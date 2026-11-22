# IllegalClassFormatException và ngoại lệ transformer không bảo đảm ngăn nạp lớp

## 1. Vì sao cần hiểu hợp đồng lỗi của ClassFileTransformer?

Trong Java Instrumentation, một `ClassFileTransformer` nhận dữ liệu class file trước khi JVM định nghĩa, định nghĩa lại hoặc retransform một lớp. Transformer có thể trả về bytecode thay thế, trả về `null` nếu không muốn thay đổi, hoặc gặp lỗi trong quá trình phân tích/biến đổi.

Trực giác dễ gây nhầm là: **"Transformer ném ngoại lệ nghĩa là JVM sẽ hủy thao tác nạp lớp."** Theo hợp đồng `java.lang.instrument.ClassFileTransformer` của Java SE 17, điều đó **không đúng**. Nếu `transform` ném ngoại lệ không tự bắt, **những transformer đứng sau vẫn được gọi** và JVM vẫn **cố gắng** thực hiện load/redefine/retransform. Đối với việc lựa chọn đầu ra của transformer đang lỗi, ném ngoại lệ có hiệu lực giống **trả `null`**.

Nội dung cần phân biệt rõ:

1. **`IllegalClassFormatException`** là tín hiệu mà một transformer có thể ném khi cho rằng **đầu vào classfile không hợp lệ**.
2. Ngoại lệ của callback transformer **không phải mệnh lệnh ngăn JVM nạp lớp**.
3. **`return null`**, **throw từ transformer**, và **return một mảng bytecode không hợp lệ** là ba hành vi khác nhau.
4. JVM vẫn có thể thất bại khi **bytecode cuối cùng không hợp lệ**, gặp lỗi liên kết, không có class phụ thuộc hoặc lỗi khởi tạo lớp.
5. Nếu bắt buộc từ chối một thao tác vì chính sách, **đừng dùng ngoại lệ transformer như một cơ chế kiểm soát truy cập đáng tin cậy**.

Mục tiêu của bài là đọc đúng hợp đồng API, biết điều gì được bảo đảm và điều gì không, tự kiểm chứng bằng Java 17+, và thiết kế transformer an toàn trước lỗi.

## 2. Đường đi của bytecode qua nhiều transformer

Giả sử một agent đăng ký hai transformer, A rồi B, trong cùng nhóm thứ tự:

~~~text
ClassLoader / JVM yêu cầu định nghĩa demo.Target
              |
              v
        classfile bytes gốc
              |
              v
       Transformer A
          /        \
     return bytes   throw exception / return null
          |                     |
     bytes mới                 bytes trước A
          \                     /
           v                   v
                Transformer B
                     |
               bytes hoặc null
                     |
                     v
                JVM kiểm tra bytes
                     |
           +---------+---------+
           |                   |
     bytes hợp lệ         bytes không hợp lệ
           |                   |
      định nghĩa lớp       lỗi định dạng/xác minh
~~~

**Ngữ nghĩa quan trọng:**

- Nếu transformer **trả `null`**, nó không thay đổi bytecode; transformer tiếp theo được xét trên bytes đang có.
- Nếu transformer **trả `byte[]` mới**, output của nó trở thành input của transformer tiếp theo.
- Nếu transformer **ném ngoại lệ**, JVM vẫn gọi các transformer sau và vẫn thử thao tác class tương ứng. Về dòng bytes, hiệu lực của callback này giống trả `null`.
- Việc JVM **thử** định nghĩa lớp không có nghĩa **định nghĩa lớp chắc chắn thành công**. Sau callback, class file còn phải được kiểm tra và liên kết theo quy tắc JVM.
- Những hiệu ứng phụ của callback trước khi ném lỗi, chẳng hạn ghi log hoặc tăng counter, không được JVM tự hoàn nguyên. "Giống `return null`" nói đến **đầu ra biến đổi**, không phải rollback mọi hiệu ứng phụ Java.

Lưu ý thứ tự trong trường hợp tổng quát: đặc tả chia transformer theo nhóm **không hỗ trợ retransformation / hỗ trợ retransformation** và các transformer native; trong từng nhóm, thứ tự theo đăng ký. Với **hai transformer Java đăng ký qua `addTransformer(transformer)`** như demo bên dưới, cả hai đều ở cùng nhóm không hỗ trợ retransformation và chạy theo thứ tự đã đăng ký.

## 3. IllegalClassFormatException là gì?

`java.lang.instrument.IllegalClassFormatException` thuộc module `java.instrument`, kế thừa `Exception` nên là **checked exception**. Phương thức `ClassFileTransformer.transform` có thể khai báo `throws IllegalClassFormatException`.

Ý nghĩa theo Javadoc: transformer báo rằng **tham số đầu vào của nó** không biểu diễn class file hợp lệ. Nguyên nhân có thể là class bytes ban đầu hỏng, hoặc **một transformer trước đó** trả bytes bị hỏng.

~~~java
@Override
public byte[] transform(ClassLoader loader, String className,
        Class<?> classBeingRedefined, ProtectionDomain protectionDomain,
        byte[] classfileBuffer) throws IllegalClassFormatException {
    // Nếu phân tích thấy input không đúng định dạng:
    throw new IllegalClassFormatException("unexpected classfile input");
}
~~~

Đây là **trích đoạn minh họa**, không phải lớp Java chạy độc lập. Trong transformer production, cần thực sự **kiểm tra dữ liệu** trước khi kết luận format lỗi; không ném ngoại lệ này vô điều kiện cho mọi class.

**Hiệu lực:** JVM bỏ qua kết quả biến đổi của callback đang ném lỗi, tiếp tục gọi các transformer sau và vẫn thử load/redefine/retransform. `IllegalClassFormatException` giúp công cụ và người phát triển **nhận diện/nghiên cứu lỗi format**; nó **không phải điều kiện từ chối class loading**.

Hai câu dưới đây khác nhau:

- **"Transformer A phát hiện đầu vào bất thường và ném `IllegalClassFormatException`."** Đây là tín hiệu của **A**, không phải kết luận cuối cùng của JVM.
- **"JVM không thể định nghĩa lớp vì class file cuối cùng sai định dạng."** Đây là lỗi kiểm tra class của JVM, có thể biểu hiện dưới dạng **`ClassFormatError`**.

Nếu class gốc thực sự hỏng và không transformer nào sửa được, việc A ném `IllegalClassFormatException` không cứu lớp khỏi lỗi về sau. Ngược lại, nếu class gốc hợp lệ nhưng A ném lỗi do bug của chính A, JVM có thể tiếp tục nạp lớp **bình thường** từ bytes hợp lệ.

## 4. Các kết quả có thể xảy ra ở callback

| Hành vi trong `transform` | Các transformer còn lại | JVM có thử thao tác class? | Kết quả có thể quan sát |
|---|---|---|---|
| `return null;` | Có | Có | Class vẫn nạp được nếu bytes cuối hợp lệ |
| `throw new IllegalClassFormatException(...);` | Có | Có | Callback này bị bỏ qua về mặt bytes, lớp vẫn có thể nạp |
| `throw new IllegalStateException(...);` | Có | Có | Runtime exception của callback không phải cơ chế chặn lớp |
| `return transformedBytes;`, bytes hợp lệ | Có, nhận output mới | Có | Lớp có thể dùng bytecode mới nếu mọi kiểm tra thành công |
| `return malformedBytes;` | Có, nhận bytes đã hỏng | Có | JVM có thể ném `ClassFormatError` hoặc lỗi kiểm tra/liên kết tương ứng |
| Lỗi trong `premain` hoặc `agentmain` ngoài callback | Không áp dụng quy tắc của callback | Phụ thuộc kiểu khởi tạo agent | Khởi tạo agent có thể thất bại theo quy tắc riêng |

**Không đánh đồng "ngoại lệ đã bị bỏ qua tại transform" với "toàn bộ JVM miễn nhiễm trước mọi lỗi".** Một transformer có thể gây side effect không an toàn, trả bytes sai hoặc gọi vào mã gây vấn đề về class loading. Hợp đồng chỉ bảo đảm hướng xử lý **ngoại lệ callback** và nỗ lực tiếp tục pipeline, không bảo đảm ứng dụng cuối cùng luôn chạy.

## 5. Thí nghiệm Java 17+: lỗi callback nhưng class vẫn nạp

Ta sẽ tạo một startup agent với **hai transformer**. Transformer đầu có ba chế độ: ném `IllegalClassFormatException`, ném `IllegalStateException` hoặc **trả bytes sai định dạng**. Transformer thứ hai chỉ in dấu hiệu đã được gọi và trả `null`. Ứng dụng sẽ gọi một phương thức trên `demo.Target`.

Ví dụ dùng duy nhất JDK 17+, không dùng thư viện thứ ba và có thể chạy trên Windows, Linux hoặc macOS nếu đã cài JDK đầy đủ.

### 5.1. Thư mục dự án

~~~text
transformer-failure-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── demo/
│   │       └── FailureAgent.java
│   └── app/
│       └── demo/
│           ├── Target.java
│           └── Main.java
└── out/                    # tạo khi build
    ├── agent/
    ├── app/
    └── failure-agent.jar
~~~

Chỉ ba tệp Java là đủ; mã của agent và ứng dụng được biên dịch ra **hai thư mục class khác nhau** để tách rõ trách nhiệm.

### 5.2. Tệp FailureAgent.java

Lưu tại **`src/agent/demo/FailureAgent.java`**:

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class FailureAgent {
    public static void premain(String mode, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                    Class<?> redefined, ProtectionDomain domain,
                    byte[] original) throws IllegalClassFormatException {
                if (!"demo/Target".equals(className)) {
                    return null;
                }

                System.out.println("first:" + mode);

                if ("checked".equals(mode)) {
                    throw new IllegalClassFormatException(
                            "demo format signal");
                }

                if ("runtime".equals(mode)) {
                    throw new IllegalStateException(
                            "demo runtime fault");
                }

                if ("badbytes".equals(mode)) {
                    return new byte[] { 0x01, 0x02, 0x03 };
                }

                return null;
            }
        });

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                    Class<?> redefined, ProtectionDomain domain,
                    byte[] bytes) {
                if ("demo/Target".equals(className)) {
                    System.out.println("second:called");
                }
                return null;
            }
        });
    }
}
~~~

**Phân tích:**

1. Hai transformer được đăng ký **theo thứ tự** bằng `inst.addTransformer(...)`, mặc định là không hỗ trợ retransformation.
2. Bộ lọc `"demo/Target".equals(className)` để tránh xử lý vô tình các class của JDK/agent. Tên class trong callback dùng **dấu gạch chéo `/`** theo dạng tên nội bộ JVM.
3. Với **`checked`**, transformer A ném **`IllegalClassFormatException`** dù bytes gốc của demo là hợp lệ. Đây là hành vi **cố ý để kiểm tra quy tắc xử lý lỗi**, không phải kiểu kiểm tra format nên dùng ngoài thực tế.
4. Với **`runtime`**, transformer A ném **`IllegalStateException`**, một unchecked exception. Nó không tự biến thành lệnh hủy load.
5. Với **`badbytes`**, transformer A **trả** một mảng ba byte không phải class file, để phân biệt **đầu ra hỏng** với **việc ném exception**.
6. Transformer B in **`second:called`** nếu nhận callback của `Target`. Nếu A ném lỗi, B vẫn phải được JVM gọi; nếu A trả bytes hỏng, B cũng được gọi với bytes từ A.
7. Transformer B trả `null` nên không thay bytes đang đi tiếp trong pipeline.

**Vì sao override phương thức 5 tham số?** Java 17 hỗ trợ cả phiên bản `transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])`. Implementation mặc định của phiên bản 6 tham số ủy quyền cho phiên bản 5 tham số nếu không được override, nên mã ví dụ hợp lệ trong Java 17.

Không sửa trực tiếp mảng `original` hoặc `bytes` truyền vào. Hợp đồng quy định transformer phải **tạo byte array mới** nếu muốn biến đổi, và trả `null` nếu không có thay đổi.

### 5.3. Tệp Target.java

Lưu tại **`src/app/demo/Target.java`**:

~~~java
package demo;

public final class Target {
    public static String message() {
        return "TARGET-OK";
    }
}
~~~

Đây là class mà agent theo dõi; không chứa instrumentation và không gọi agent trực tiếp.

### 5.4. Tệp Main.java

Lưu tại **`src/app/demo/Main.java`**:

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("main:" + Target.message());
    }
}
~~~

Lớp `Target` được sử dụng khi `main` chạy, **sau** khi `premain` của startup agent hoàn tất việc đăng ký transformer.

### 5.5. Manifest của agent

Lưu tại **`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.FailureAgent

~~~

Giữ **newline ở cuối tệp**. `Premain-Class` cho Java launcher biết class nào có `premain`. Không cần `Can-Retransform-Classes` vì bài này chỉ kiểm tra quá trình **nạp class lần đầu**, không gọi `retransformClasses`.

### 5.6. Biên dịch và đóng gói

Tại thư mục **`transformer-failure-lab`**, trong Bash:

~~~bash
mkdir -p out/agent out/app
~~~

Hoặc PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app
~~~

Các lệnh JDK sau có thể chạy trong cả hai môi trường khi đang ở thư mục gốc:

~~~bash
javac --release 17 -d out/agent src/agent/demo/FailureAgent.java
javac --release 17 -d out/app src/app/demo/Target.java src/app/demo/Main.java
jar --create --file out/failure-agent.jar --manifest agent.mf -C out/agent .
jar --list --file out/failure-agent.jar
~~~

JAR phải có các entry quan trọng:

~~~text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/FailureAgent.class
~~~

Các class ứng dụng nằm ở **`out/app`**, còn agent nằm trong **`out/failure-agent.jar`**. Không cần biến ứng dụng thành executable JAR cho bài này.

### 5.7. Trường hợp A: ném IllegalClassFormatException

Chạy:

~~~bash
java -javaagent:out/failure-agent.jar=checked -cp out/app demo.Main
~~~

**Stdout** của bài demo:

~~~text
first:checked
second:called
main:TARGET-OK
~~~

**Giải thích bằng chứng:** Transformer A đã ném `IllegalClassFormatException`. Transformer B **vẫn được gọi**. Class `Target` hợp lệ, nên JVM có thể nạp và chạy nó; `Main` in **`TARGET-OK`**. Chương trình kết thúc thành công.

Kết quả này bác bỏ suy luận "ném `IllegalClassFormatException` chắc chắn làm `ClassLoader` từ chối class".

### 5.8. Trường hợp B: ném một RuntimeException

Chạy:

~~~bash
java -javaagent:out/failure-agent.jar=runtime -cp out/app demo.Main
~~~

Stdout:

~~~text
first:runtime
second:called
main:TARGET-OK
~~~

Ngoại lệ **`IllegalStateException`** do transformer A ném **cũng không chặn** transformer B và quá trình nạp `Target` trong demo. Đây là lỗi callback, không đồng nghĩa JVM thấy classfile cuối cùng sai định dạng.

**Cẩn trọng:** Kết quả này không cho phép coi mọi loại lỗi nặng trong transformer đều vô hại. Ví dụ lỗi hết bộ nhớ, deadlock, thay đổi state toàn cục hoặc transformer ném sai bytes có thể gây tác động nghiêm trọng. Mệnh đề chính của Javadoc là **ngoại lệ từ callback không tự tạo cơ chế fail-closed**.

### 5.9. Trường hợp C: trả bytes không phải class file

Chạy:

~~~bash
java -javaagent:out/failure-agent.jar=badbytes -cp out/app demo.Main
~~~

Đầu stdout của demo:

~~~text
first:badbytes
second:called
~~~

Trong trường hợp này **không có** dòng `main:TARGET-OK`. Với HotSpot JDK kiểm thử, **stderr** chứa:

~~~text
Exception in thread "main" java.lang.ClassFormatError: Truncated class file
~~~

và stack trace tiếp theo; tiến trình kết thúc với mã khác 0. Thông báo chi tiết có thể khác giữa JVM/JDK nên không coi toàn bộ stack trace là output cố định.

**Điều khác biệt:** A **không ném `IllegalClassFormatException`** ở mode này. A **trả bytes hỏng**. B vẫn được gọi nhưng trả `null`, vì vậy bytes hỏng đi tiếp đến bước JVM xác minh. JVM không thể định nghĩa `Target` từ bytecode đó và báo **`ClassFormatError`**. Lỗi đến từ **classfile cuối cùng**, không phải tín hiệu exception của callback A.

### 5.10. Bảng bằng chứng

| Mode của agent | A làm gì? | B có chạy? | `main:TARGET-OK` có xuất hiện? | Kết luận |
|---|---|---|---|---|
| `checked` | Ném `IllegalClassFormatException` | Có | Có | Exception callback không chặn class hợp lệ |
| `runtime` | Ném `IllegalStateException` | Có | Có | Unchecked exception callback không phải fail-closed |
| `badbytes` | Trả mảng class bytes sai định dạng | Có | Không | JVM có thể từ chối bytes cuối bằng `ClassFormatError` |

Thí nghiệm kiểm tra **định nghĩa lớp lần đầu**. Nó không yêu cầu retransform hay sửa class đang hoạt động.

## 6. Ranh giới giữa lỗi transformer và lỗi JVM

### 6.1. Không gộp IllegalClassFormatException với ClassFormatError

| Đặc điểm | `IllegalClassFormatException` | `ClassFormatError` |
|---|---|---|
| Kiểu Java | Checked exception, kế thừa `Exception` | Error, kế thừa `LinkageError` |
| Xuất hiện ở đâu? | Transformer có thể ném khi cho rằng input không hợp lệ | JVM có thể ném khi classfile dùng để định nghĩa/retransform không hợp lệ |
| Vai trò | Tín hiệu chẩn đoán trong callback | Báo thao tác class thất bại ở tầng kiểm tra/định nghĩa |
| Tự chặn load không? | Không, chỉ là lỗi tại callback đó | Có thể làm chính thao tác class thất bại |
| Bắt/catch thế nào? | Khai báo trong `transform` hoặc xử lý tại transformer | Thường là lỗi nghiêm trọng phải tìm và sửa classfile/transformer |

`ClassFormatError` **không phải** một phiên bản unchecked của `IllegalClassFormatException`. Không nên ném `ClassFormatError` trong transformer với mục đích kiểm soát class loading; phải phân biệt **lỗi do callback gây ra** với **lỗi bytecode cuối** mà VM tự phát hiện.

### 6.2. Lỗi xảy ra ở bước khác sẽ có quy tắc khác

Hợp đồng `ClassFileTransformer.transform` không bao trùm mọi đoạn code có thể lỗi:

- **Trong `premain` của startup agent:** lỗi chưa xử lý có thể làm JVM không hoàn tất khởi động ứng dụng.
- **Trong `agentmain` của agent attach:** quy tắc khởi tạo khác; thất bại thường được báo về attach helper và không mặc nhiên khiến JVM đích thoát, nhưng side effects agent đã thực hiện có thể còn.
- **Trong ClassLoader hoặc khi liên kết:** `ClassNotFoundException`, `NoClassDefFoundError`, `VerifyError`, `UnsupportedClassVersionError`, `ClassCircularityError` và các lỗi khác có thể xảy ra độc lập với việc transformer có ném gì hay không.
- **Trong `Instrumentation.retransformClasses`:** nếu bytes cuối không hợp lệ, API có thể ném `ClassFormatError` hoặc lỗi được đặc tả; nếu thao tác retransform trả lỗi, tài liệu API nói **không có lớp nào trong tập được retransform thành công**.
- **Trong mã ứng dụng khi sử dụng class:** các lỗi initializer, null, race hoặc nghiệp vụ vẫn có thể xảy ra sau khi class đã được nạp hợp lệ.

Điều cần ghi nhớ là **"throw trong callback không chặn load" không có nghĩa "load không thể thất bại"**.

## 7. Chuỗi nhiều transformer và lỗi liên hoàn

Một ứng dụng có thể được instrument bởi nhiều agent hoặc thư viện, nên **input của transformer N không nhất thiết là bytes gốc**. Thứ tự áp dụng làm thay đổi kết quả:

~~~text
bytes gốc hợp lệ
    |
Transformer A: trả bytes biến đổi
    |
Transformer B: nhận output của A
    |
Transformer C: nhận output của B
    |
JVM xác minh bytes cuối
~~~

Giả sử A trả bytes hỏng. B kiểm tra và ném `IllegalClassFormatException`. JVM **không dừng pipeline chỉ vì B ném exception**. Nếu không transformer nào sửa lại bytes đang có, JVM vẫn có thể từ chối bytes cuối. Ngược lại, nếu B chỉ bị lỗi logic trong khi bytes từ A hợp lệ, các transformer còn lại/JVM vẫn có thể tiếp tục bình thường.

Đặc tả cũng quy định **không sửa trực tiếp `classfileBuffer`**; muốn biến đổi thì tạo `byte[]` mới. Sửa mảng input tại chỗ rồi ném exception là vi phạm hợp đồng và không được suy rằng JVM sẽ tự khôi phục bytes về trạng thái trước sửa.

Một vấn đề khác: **transformer không nên đăng ký lặp cùng một instance**. API cho phép nhưng tài liệu khuyến cáo tránh; nhiều callback trùng nhau có thể tăng overhead hoặc chèn instrument hai lần. Khi cần theo dõi lỗi, ghi rõ tên transformer, class, class loader, thời điểm, phiên bản agent và loại callback.

## 8. Chiến lược xử lý lỗi hợp lý trong transformer

### 8.1. Phân loại trước khi quyết định

| Tình huống | Hành vi nên cân nhắc |
|---|---|
| Lớp không nằm trong phạm vi instrument | Trả `null` ngay, không phân tích bytecode thừa |
| Phân tích thành công và cần thay đổi | Tạo `byte[]` mới hợp lệ; trả bytes đã kiểm tra |
| Không cần hoặc không thể instrument lớp này | Trả `null`, ghi metric skip nếu cần |
| Phát hiện input classfile thực sự sai định dạng | Có thể ném `IllegalClassFormatException` phục vụ chẩn đoán, nhưng đừng coi nó là chặn class |
| Bug nội bộ khi tạo output | Ghi nguyên nhân trong giới hạn an toàn; không phát tán bytes hỏng; cân nhắc trả `null` để giữ app hoạt động |
| Yêu cầu chính sách phải chặn tải lớp | Áp dụng cơ chế kiểm soát tại điểm có quyền từ chối thật sự (đường build/deployment, môi trường, class loader được kiểm soát), không dựa trên exception transformer |

Hợp đồng API nói transformer có thể bắt **`Throwable`** để tránh những bất ngờ do unchecked exceptions. Tuy vậy, trong mã ứng dụng production không nên dùng một `catch(Throwable)` rộng mà **âm thầm nuốt mọi lỗi nghiêm trọng** như hết bộ nhớ. Tổ chức cần định nghĩa rõ các loại lỗi có thể khôi phục, logging tối thiểu và cách vô hiệu hóa instrumenter an toàn.

### 8.2. Mẫu xử lý fail-open và telemetry

**Fail-open** có nghĩa: nếu **chỉ lớp instrumenter bị lỗi**, mục tiêu là để **bytecode gốc hợp lệ tiếp tục được JVM xử lý**; bỏ qua instrument thay vì làm hỏng ứng dụng. Đây là chính sách thiết kế có chủ đích, không phải cam kết rằng mọi lỗi đều có thể phục hồi.

Mã minh họa dùng trong một transformer đã có bộ lọc:

~~~java
try {
    byte[] result = performSafeRewrite(classfileBuffer);
    return result; // Bắt buộc là classfile hợp lệ, mảng mới.
} catch (KnownRewriteException ex) {
    recordFailure(className, ex);
    return null; // Không áp dụng transform của callback này.
}
~~~

**Đây chỉ là đoạn minh họa cấu trúc xử lý lỗi**, không phải chương trình biên dịch độc lập; `performSafeRewrite`, `KnownRewriteException` và `recordFailure` là các thành phần cần được triển khai theo thư viện bytecode và hệ thống telemetry của bạn.

Các nguyên tắc thiết kế:

1. **Lọc nhanh:** kiểm tra tên class, module và loader trước khi phân tích. Tránh instrument class của agent hoặc thư viện nền của chính nó.
2. **Không mutate buffer input:** sao chép khi cần, tạo output mới, và đảm bảo cấu trúc class hợp lệ.
3. **Bắt lỗi có phạm vi:** xử lý lỗi dự kiến từ parser/rewrite; ghi thông tin đủ để điều tra nhưng giới hạn số log vì transformer có thể chạy rất thường xuyên.
4. **Không tin vào throw để từ chối:** kiểm soát bảo mật phải nằm ở điểm có quyền từ chối và có thể được kiểm chứng riêng.
5. **Kiểm thử chain:** khi có nhiều transformer, kiểm tra kết quả ngay cả khi một callback lỗi.
6. **Đo chất lượng instrumentation:** số class được xử lý, số class bị skip, số lần exception, độ trễ transform và tác động tới startup/runtime.
7. **Thử cả load và retransform nếu agent hỗ trợ:** cùng một callback có thể gặp bytes khác nhau và quy tắc hợp lệ của redefinition.

Không in stack trace toàn bộ từ mỗi lần `transform` trên hot path; có thể gây I/O lớn, class loading recursion hoặc làm mất khả năng chẩn đoán lúc lỗi tăng nhanh.

## 9. Điều gì thay đổi trong redefine và retransform?

Mệnh đề về exception callback còn áp dụng khi class được **định nghĩa lại** hoặc **retransform**. Tuy nhiên, quy trình đầy đủ có điều kiện khác:

- Transformer được đăng ký với `canRetransform=true` mới nhận callback mới trong mỗi retransformation. Transformer không hỗ trợ sẽ được JVM tái sử dụng kết quả biến đổi trước theo hợp đồng.
- Nếu callback throw trong retransformation, **những transformer sau vẫn được gọi** và JVM vẫn thử thao tác. Không hiểu throw là hủy yêu cầu.
- Nếu **bytes cuối** sau toàn bộ biến đổi sai, `retransformClasses` có thể báo lỗi; Javadoc quy định khi lời gọi retransform ném exception, **không lớp nào trong yêu cầu đó được retransform**.
- JVM áp dụng các ràng buộc thay đổi cấu trúc class. Ngay cả bytes được parse thành công cũng có thể không phải một **redefinition hợp lệ** của class đã tải.
- Trên class đang được thread sử dụng, nếu retransform thành công, active frames có thể tiếp tục bytecode cũ, còn lời gọi mới dùng bytecode mới.

Vì vậy, cần phân biệt **transformer nhận callback**, **transformer trả output**, **JVM xác minh và áp dụng output**, và **ứng dụng quan sát được hành vi mới**. Đây là các cột mốc riêng, đặc biệt khi có lỗi.

## 10. Sai lầm thường gặp

**Sai lầm 1 — "Throw IllegalClassFormatException để từ chối class nguy hiểm."**  
Không đúng hợp đồng. JVM tiếp tục gọi các transformer sau và thử load. Muốn kiểm soát chính sách, cần một điểm chặn được đặc tả khác.

**Sai lầm 2 — "Transformer bị RuntimeException thì cả JVM chắc chắn dừng."**  
Sai. Trong demo, exception của callback được xử lý theo hợp đồng, lớp vẫn nạp. Không suy ra ứng dụng luôn an toàn nếu callback có side effect hoặc lỗi VM khác.

**Sai lầm 3 — "Có ClassFormatError nghĩa là một transformer đã ném IllegalClassFormatException."**  
Không nhất thiết. Class bytes đầu vào hoặc **output cuối** có thể sai; lỗi do JVM phát hiện không chứng minh một callback đã ném checked exception.

**Sai lầm 4 — "Return null nghĩa là không có gì xảy ra."**  
Nó chỉ nghĩa **callback không cung cấp bytes thay thế**. Callback vẫn có thể ghi log, thay state, tiêu tốn thời gian hoặc gây lỗi phụ.

**Sai lầm 5 — "Nếu A throw thì B không chạy."**  
Trái tài liệu. JVM vẫn gọi B và các transformer tiếp theo theo quy trình.

**Sai lầm 6 — "Cứ catch Throwable và im lặng là an toàn."**  
Nguy hiểm. Có lỗi nghiêm trọng không phù hợp để bỏ qua; ít nhất cần phân loại, logging có kiểm soát và kế hoạch vận hành.

**Sai lầm 7 — "Transformer trả bytes sai thì JVM sẽ tự fallback về bytes gốc."**  
Không có quy tắc fallback chung như vậy. Return bytes hỏng và throw exception là hai kết quả khác nhau; JVM có thể từ chối thao tác ở bước xác minh.

**Sai lầm 8 — "Mọi callback dùng cùng bytecode đầu vào."**  
Sai. Output từ transformer trước trở thành input của transformer sau, trừ trường hợp trước đó trả `null` hoặc ném exception.

## 11. Bài tập kiểm chứng

### Bài tập A — dự đoán trước khi chạy

Trước khi chạy ba mode ở mục 5, ghi ra dự đoán:

1. Có in `second:called` sau `first:checked` hay không?
2. Có in `main:TARGET-OK` sau `first:runtime` hay không?
3. Mode `badbytes` có ném `IllegalClassFormatException` từ Java code không, hay thất bại ở bước xác minh class của JVM?

Đối chiếu với stdout/stderr thực tế. Kết quả chính: **checked và runtime không tự chặn**, còn bytes hỏng có thể khiến JVM từ chối class.

### Bài tập B — cho transformer thứ hai sửa class hợp lệ

Mở rộng transformer B bằng thư viện bytecode đáng tin cậy như ASM hoặc Byte Buddy để thay một phương thức nhưng vẫn bảo đảm class file hợp lệ. Chạy khi A ném `IllegalClassFormatException`. Nếu B trả bytes hợp lệ và JVM chấp nhận, bạn có thể chứng minh **ngoại lệ A không ngăn B áp dụng transform**. Đây là bài tập nâng cao; thư viện cần được cấu hình riêng, không nằm trong demo JDK thuần.

### Bài tập C — thử input xấu và lỗi parse

Trong một môi trường kiểm thử cô lập, thay output của A bằng bytes class file hỏng như mode `badbytes`. Hỏi: B nhận cái gì? Lỗi cuối do lớp nào phát ra? Giải thích lý do không nên dựa vào exception callback để dự đoán kết quả verifier.

### Bài tập D — nêu chiến lược production

Giả sử instrumenter parser lỗi trên 2% class của framework nhưng class gốc vẫn hợp lệ. Hãy thiết kế cách log một mẫu lỗi có giới hạn, tăng counter lỗi và trả `null` cho những class không thể instrument; sau đó đo ứng dụng có tiếp tục chạy và độ phủ telemetry còn lại.

### Tự kiểm tra ngắn

- **`IllegalClassFormatException` có ép JVM hủy nạp class không?** Không. Nó có hiệu lực như trả `null` tại callback đang lỗi.
- **Transformer sau có còn chạy khi transformer trước throw không?** Có, theo hợp đồng.
- **`return new byte[]{1,2,3}` có giống `throw IllegalClassFormatException` không?** Không. Trả bytes hỏng có thể khiến JVM từ chối class bằng `ClassFormatError`.
- **`ClassFormatError` là checked exception từ callback?** Không. Nó là một `LinkageError` do JVM có thể phát sinh khi bytes class không hợp lệ.
- **Exception callback có bảo đảm lớp nạp thành công?** Không. JVM vẫn cần xác minh, liên kết và chạy mã liên quan.
- **Cơ chế nào phù hợp để đo lỗi transformer?** Ghi counter/log có giới hạn, phân biệt callback lỗi và JVM class failure, không suy luận từ một dấu hiệu duy nhất.

## 12. Kết luận và tài liệu tham chiếu

**Hợp đồng của `ClassFileTransformer` quy định ngoại lệ ném ra từ `transform` không phải lệnh ngăn nạp lớp.** Các transformer tiếp theo vẫn được gọi và thao tác load/redefine/retransform vẫn được JVM thử thực hiện. **`IllegalClassFormatException`** là một tín hiệu chẩn đoán input classfile bất thường, có hiệu lực giống trả `null` trong callback đó.

Để xác định lớp cuối cùng có chạy được không, phải xem **bytes sau toàn bộ pipeline**, các bước xác minh của JVM và những lỗi độc lập khác. Thiết kế agent nên trả `null` khi không thể biến đổi an toàn, ghi lỗi có kiểm soát, kiểm thử nhiều transformer nối tiếp và đặt cơ chế từ chối class ở đúng lớp kiểm soát thay vì phụ thuộc vào throw từ transformer.

**Tài liệu chuẩn của Java SE 17:**

- [ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html) — thứ tự callback, hợp đồng `null`/exception, bytes và hai chữ ký `transform`.
- [IllegalClassFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/IllegalClassFormatException.html) — mục đích exception checked khi input classfile không hợp lệ.
- [Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html) — đăng ký transformer, thứ tự và lỗi trong retransformation.
- [ClassFormatError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassFormatError.html) — lỗi JVM phát hiện class file sai định dạng.
