# Phân giải sớm, phân giải muộn và thời điểm xuất hiện lỗi trong JVM

> **Chủ đề:** Java Core → ClassLoader → Vòng đời lớp. Bài học phân biệt thời điểm JVM phân giải (*resolve*) tham chiếu ký hiệu với thời điểm lỗi liên kết (*linkage error*) được ném tới chương trình. Các thí nghiệm dùng Java 17+ và kiểm tra được trên OpenJDK 21.

## 1. Vấn đề: chương trình khởi chạy rồi mới báo thiếu method

Giả sử ta biên dịch `App.class` với phiên bản thư viện `Api` có phương thức `message()`. Sau khi biên dịch, thư viện được thay bằng bản không còn phương thức đó, nhưng `App.class` vẫn giữ nguyên.

Tại sao `main` có thể in một số dòng rồi đến lúc gọi `Api.message()` mới xuất hiện `NoSuchMethodError`? JVM có bắt buộc đợi đến chính lời gọi mới được tìm phương thức hay không?

Câu trả lời có hai phần:

- JVM có quyền **phân giải sớm (eager resolution)** nhiều tham chiếu ký hiệu hoặc **phân giải muộn (lazy resolution)** khi cần. Chiến lược nội bộ có thể khác nhau giữa các JVM và các tình huống.
- Dù đã phát hiện lỗi sớm bên trong, JVM vẫn phải bảo đảm lỗi chỉ trở nên **quan sát được tại điểm chương trình thực hiện hành động có thể, trực tiếp hoặc gián tiếp, cần liên kết tới đối tượng đang lỗi**. Không thể kết luận chiến lược eager hay lazy chỉ từ dòng output xuất hiện trước lỗi.

Đó là ranh giới giữa **thời điểm thực hiện resolution** và **thời điểm công khai lỗi ra chương trình**.

## 2. Đặt resolution vào vòng đời lớp

Một class file ghi các **symbolic reference** trong run-time constant pool, chẳng hạn `Methodref demo/Api.message:()Ljava/lang/String;`. **Resolution** dùng tên, descriptor và loader để tìm đúng lớp hoặc thành viên runtime. **Linking** gồm verification, preparation và resolution; verification và preparation phải hoàn tất trước initialization, còn resolution có thể đến sau. Từ nền tảng đó, bài này tập trung vào **lịch resolution và điểm chương trình quan sát lỗi**, không lặp lại thuật toán tra cứu thành viên.

## 3. Phân giải sớm và phân giải muộn

### Eager resolution

JVM có thể resolve nhiều symbolic reference khi verify/link class, trước lúc bytecode trực tiếp sử dụng chúng. Việc này có thể giúp chuẩn bị metadata và phát hiện dependency không phù hợp sớm ở nội bộ.

### Lazy resolution

JVM có thể để từng symbolic reference chưa resolve cho đến khi instruction sử dụng nó, chẳng hạn lần đầu thực thi `invokestatic` tới phương thức hoặc `getstatic` tới field. Cách này tránh làm công việc không cần thiết cho phần code không dùng đến.

### Chính xác JVM bảo đảm điều gì?

JVMS 5.4 và 5.4.3 cho phép các chiến lược trên **miễn không làm đổi ngữ nghĩa quan sát được**. Eager/lazy là chiến lược triển khai; Java không có yêu cầu rằng HotSpot hoặc mọi JVM phải resolve mọi reference ở cùng một thời điểm.

| Vấn đề | Có được bảo đảm không? |
| --- | --- |
| Class được nạp trước khi liên kết | Có. |
| Verification và preparation hoàn tất trước initialization | Có. |
| Tất cả symbolic reference được resolve trước initialization | Không. |
| JVM có thể resolve sớm các symbolic reference thông thường | Có, với giới hạn JVMS. |
| Lỗi linking được ném ở điểm hành động có thể trực tiếp/gián tiếp cần linking liên quan | Có. |
| Quan sát lỗi tại lời gọi chứng minh nội bộ JVM dùng lazy resolution | Không. |

**Ngoại lệ quan trọng:** Một số loại reference có quy tắc riêng. *Dynamically-computed constant* không được resolve tùy ý trước khi instruction `ldc`/`ldc_w`/`ldc2_w` cần dùng hoặc trước tình huống bootstrap sử dụng nó làm static argument như JVMS quy định; dynamic call site của `invokedynamic` cũng bị ràng buộc theo quy tắc bootstrap. Do đó không nên tuyên bố “JVM được resolve bất kỳ mục nào trong constant pool ngay lúc load”.

## 4. Hai mốc thời gian phải tách riêng

Xét `App.class` tham chiếu `Api.message()`, trong khi bản `Api.class` thực chạy không còn method tương ứng:

```text
App.class (compile với Api v1)
      |
      | contains Methodref demo/Api.message:()String
      v
JVM nạp App
      |
      +--> JVM có thể eager resolve và phát hiện thiếu method nội bộ
      |
      +--> main: println("started")
      |
      +--> nhánh không gọi method: có thể kết thúc bình thường
      |
      '--> nhánh thực thi invokestatic Api.message()
                      |
                      '--> NoSuchMethodError được quan sát
                           ở hành động sử dụng reference
```

Trên một JVM triển khai lazy, kiểm tra method có thể được thực hiện tại chính instruction cần dùng. Trên một JVM eager, vấn đề có thể được phát hiện trước nhưng việc ném ra chương trình vẫn phải nằm trong giới hạn JVMS.

**Đây là quy tắc về hành vi quan sát được**, không phải lời hứa mọi lỗi chỉ được ném đúng tại một dòng source. Liên kết có thể xảy ra gián tiếp; verification, loading của superclass/interface hoặc một thao tác chủ động khác có thể làm chương trình thấy lỗi tại điểm sớm hơn dự đoán từ source code.

### Kết quả resolution có được ghi nhớ?

Theo JVMS 5.4.3, với các loại reference thông thường:

- Nếu resolution thành công, các lần resolve sau đối với **cùng symbolic reference** tiếp tục thành công với cùng thực thể.
- Nếu lần đầu thất bại, các lần sau đối với **cùng reference** sẽ thất bại với cùng lỗi.
- Có các chi tiết riêng cho `invokedynamic`: call site resolution được gắn với từng instruction sử dụng reference, nên không nên suy rộng quy tắc bộ nhớ đệm của method reference thông thường cho mọi dynamic call site.

Từ đó, đổi JAR trên ổ đĩa trong lúc JVM đang chạy không phải cơ chế giúp tự sửa một symbolic reference đã resolution thất bại.

## 5. Thí nghiệm thực tế: Java biên dịch với API v1 nhưng chạy với API v2

Thí nghiệm này dùng một caller biên dịch trước, giữ nguyên caller và thay bytecode của thư viện lúc chạy.

Tạo các file theo cấu trúc:

```text
src-v1/demo/Api.java
src-v2/demo/Api.java
src-app/demo/App.java
```

**File `src-v1/demo/Api.java` — bản có method được dùng lúc biên dịch:**

```java
package demo;

public class Api {
    public static String message() {
        return "v1";
    }
}
```

**File `src-v2/demo/Api.java` — bản thay thế không có method `message`:**

```java
package demo;

public class Api {
    public static String other() {
        return "v2";
    }
}
```

**File `src-app/demo/App.java` — caller không được biên dịch lại:**

```java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println("1. App started");

        if (args.length == 0) {
            System.out.println("2. No API call");
            return;
        }

        System.out.println("2. About to invoke Api.message()");
        try {
            call();
        } catch (NoSuchMethodError e) {
            System.out.println("3. Caught NoSuchMethodError");
        }
    }

    static void call() {
        System.out.println(Api.message());
    }
}
```

Biên dịch theo thứ tự; `App` được compile với v1, sau đó runtime chỉ đặt v2 trước `App` trên classpath:

```bash
javac -d build/v1 src-v1/demo/Api.java
javac -cp build/v1 -d build/app src-app/demo/App.java
javac -d build/v2 src-v2/demo/Api.java
java -cp "build/v2:build/app" demo.App
java -cp "build/v2:build/app" demo.App go
```

Ở Linux/macOS, classpath separator là `:`. Trên Windows PowerShell hoặc CMD, hai lệnh chạy tương ứng là:

```powershell
java -cp "build\v2;build\app" demo.App
java -cp "build\v2;build\app" demo.App go
```

**Output lệnh không có tham số:**

```text
1. App started
2. No API call
```

**Output lệnh có tham số `go`:**

```text
1. App started
2. About to invoke Api.message()
3. Caught NoSuchMethodError
```

Đã đối chiếu kết quả bằng biên dịch và chạy trên OpenJDK 21. Hai nhánh cho thấy bytecode caller có thể tồn tại/chạy một phần dù một reference tới method bị thiếu. Việc bắt `NoSuchMethodError` trong thí nghiệm nhằm quan sát; **đây không phải cách sửa lỗi dependency trong ứng dụng thực tế**.

Để nhìn lại reference mà caller đã biên dịch:

```bash
javap -v -classpath build/app demo.App
```

Trong constant pool, tìm `Methodref` cho `demo/Api.message` và descriptor `()Ljava/lang/String;`. Chỉ số constant pool là kết quả của compiler nên không cần khớp một con số cụ thể.

Để so sánh:

1. Chạy cùng `App.class` với `Api v1`: `java -cp "build/v1:build/app" demo.App go` → in `v1` sau dòng `About to invoke...`, không báo `NoSuchMethodError`.
2. Bỏ cả `Api.class` khỏi runtime: khi cần symbolic reference đến `Api` có thể thấy `NoClassDefFoundError` do thiếu class.
3. Nếu sửa `message()` từ static thành instance method ở v2 trong khi caller vẫn dùng `invokestatic`, có thể gặp `IncompatibleClassChangeError`.
4. Nếu biên dịch lại caller với v2, `javac` báo không có `message()` ngay tại **compile time**. Thí nghiệm binary incompatibility chỉ có ý nghĩa khi caller giữ bytecode cũ.

## 6. Ví dụ riêng: class đã load/link nhưng chưa initialize

Tạo file độc lập `InitDemo.java`:

```java
public class InitDemo {
    static class Target {
        static {
            System.out.println("Target initialized");
        }
        static int value = 42;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("before lookup");
        Class.forName(
                "InitDemo$Target",
                false,
                InitDemo.class.getClassLoader()
        );
        System.out.println("after lookup; before active use");
        System.out.println("value=" + Target.value);
    }
}
```

Chạy:

```bash
javac InitDemo.java
java InitDemo
```

Output:

```text
before lookup
after lookup; before active use
Target initialized
value=42
```

`Class.forName(name, false, loader)` yêu cầu tìm/nạp và liên kết lớp nhưng không yêu cầu initialization qua lời gọi đó. Đến lúc thực hiện hành động đọc `Target.value`, JVM khởi tạo `Target` và in thông báo.

**Giới hạn của thí nghiệm:** Nó minh họa ranh giới loading/linking với initialization, **không chứng minh** mọi symbolic reference của `Target` đã resolve hoặc chưa resolve. Class đã link/initialize vẫn có thể mang symbolic references chưa được sử dụng.

Những API dễ nhầm:

| API | Ý nghĩa | Không bảo đảm |
| --- | --- | --- |
| `ClassLoader.loadClass(name)` | Yêu cầu loader tải class theo tên nhị phân; overload mặc định không yêu cầu init. | Toàn bộ constant pool của class đều resolved. |
| `Class.forName(name, false, loader)` | Tìm/nạp và liên kết lớp mà không yêu cầu init. | Chỉ đọc bytes, tuyệt đối không verify/link. |
| `Class.forName(name)` | Tìm và khởi tạo class theo quy tắc API. | Mọi tham chiếu trong class đều được eager resolve. |
| `ClassLoader.resolveClass(clazz)` | Cơ chế loader dùng để liên kết class đã load. | API public để ép resolve mọi reference trong mọi JVM. |

## 7. Những nhận định sai thường gặp

**“Thấy lỗi ở dòng gọi hàm nghĩa là JVM chắc chắn phân giải muộn.”** Sai. JVM có thể eager resolve và trì hoãn *việc ném lỗi ra chương trình* cho tới hành động sử dụng hợp lệ.

**“Không chạy nhánh chứa lời gọi lỗi thì toàn bộ quá trình chắc chắn thành công.”** Không bảo đảm chung: verification, superclass/interface loading, hoặc một hành động gián tiếp có thể phát hiện lỗi khác và yêu cầu linking. Với thí nghiệm `App` trên, nhánh không gọi method chạy bình thường; không được coi đó là luật cho mọi lỗi/class.

**“Đã `Class.forName` thành công là tất cả method và field dependencies đúng.”** Không chính xác. Việc tìm và linking class không là chứng nhận toàn bộ symbolic reference chưa dùng đã resolve thành công.

**“Lỗi xuất hiện sau startup thì phải là lỗi resolution.”** Không đúng: lỗi initialization, reflection, verifier, runtime dispatch, service loader hoặc logic ứng dụng có nguyên nhân độc lập.

**“Có thể xóa/sửa JAR đang chạy để JVM resolve lại.”** Không có bảo đảm đó. Các class đã định nghĩa và kết quả resolution có semantics gắn với runtime loader. Thay dependency cần redeploy, tạo class loader mới hoặc cơ chế instrumentation thích hợp; không sửa bằng thao tác tùy tiện lên JAR.

**“Source compile được tức runtime sẽ link được.”** Không đúng khi bytecode caller và version dependency ở runtime khác nhau. Lỗi binary compatibility thường chỉ phát sinh sau khi deploy.

## 8. Quy trình debug lỗi xuất hiện muộn

1. Ghi nhận **exception/error type, message, stack trace và mọi `Caused by`**; xác định instruction/operation đầu tiên có thể trực tiếp hoặc gián tiếp yêu cầu linking.
2. Đối chiếu **artifact biên dịch** và **artifact thực chạy**: classpath, module path, JAR version, duplicate classes và defining class loader.
3. Dùng `javap -v` cho **caller** để xem `Class`, `Methodref`, `Fieldref`, descriptor và opcode; dùng `javap` cho class runtime để xem member thật.
4. Nếu lỗi bị thiếu method/field, kiểm tra tên, descriptor, static/instance flag và access. Thay đổi return type hoặc parameters cũng thay descriptor, có thể gây linkage error dù source trông gần giống.
5. Tách loading, linking và initialization: nơi class được `loadClass`, `forName`, nơi `new`/`invokestatic`/`getstatic` chạy, và nơi static initializer phát sinh lỗi.
6. Tái tạo với hai nhánh có/không sử dụng reference như ví dụ. Quan sát thời điểm lỗi giúp xác định hành động triggering, **không là phép đo trực tiếp thời điểm JVM resolve nội bộ**.
7. Sửa dependency/version/build/deploy hoặc lỗi bytecode thực sự; không che lỗi linkage bằng `catch (LinkageError)` rồi tiếp tục phục vụ request.

Trên HotSpot, có thể bật log class loading để kiểm tra lớp đến từ đâu:

```bash
java -Xlog:class+load=info -cp "build/v2:build/app" demo.App go
```

Log tải lớp **không phải** log đầy đủ của symbolic reference resolution. Khi cần tìm chính xác chiến lược eager/lazy của một JVM, phải dựa trên công cụ chẩn đoán tương ứng phiên bản và vẫn phân biệt hoạt động nội bộ với semantics chuẩn.

## 9. Câu hỏi ôn tập

1. **Có bắt buộc mọi symbolic reference resolve trước initialization không?** Không. Verification và preparation phải hoàn thành trước initialization, còn resolution có thể tiếp diễn sau đó.
2. **Nếu JVM tìm ra method thiếu bằng eager resolution, liệu nó được ném lỗi ở bất kỳ thời điểm nào?** Không. JVMS ràng buộc điểm chương trình quan sát lỗi phải gắn với hành động trực tiếp/gián tiếp cần linkage của reference liên quan.
3. **Vì sao `App` dùng `Api v1` khi compile nhưng chạy với `Api v2` báo `NoSuchMethodError`?** Caller chứa symbolic method reference; ở runtime không tìm thấy method có tên/descriptor tương ứng.
4. **`Class.forName(name, false, loader)` thành công chứng minh điều gì?** Lớp được tìm/nạp/liên kết theo semantics API mà không yêu cầu init. Nó không chứng minh mọi symbolic reference khác sẽ resolve thành công.
5. **Thiếu file class khi `Class.forName` và thiếu class do bytecode tham chiếu có cùng loại lỗi không?** Không nhất thiết: trường hợp trước thường `ClassNotFoundException`, còn symbolic reference liên kết thất bại thường có thể dẫn tới `NoClassDefFoundError`.
6. **Vì sao không thể lấy vị trí `NoSuchMethodError` trên stack trace để kết luận JVM lazy resolve?** Vì eager resolution cũng có thể phát hiện lỗi trước, nhưng việc ném lỗi phải phù hợp điểm sử dụng theo JVMS.

## 10. Nguồn chuẩn

- [JVMS 5.3 — Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): loading và định danh runtime class.
- [JVMS 5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4): lựa chọn eager/lazy, lỗi linking, ràng buộc ném lỗi.
- [JVMS 5.4.3 — Resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3): các loại symbolic reference, hành vi khi resolution thành công/thất bại.
- [JVMS 5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5): điều kiện và trình tự initialization.
- [JLS 12.2–12.4 — Execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): góc nhìn Java Language Specification về nạp, liên kết và khởi tạo lớp.
- [Java 17 Class.forName API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): đối số `initialize` và class loader.
