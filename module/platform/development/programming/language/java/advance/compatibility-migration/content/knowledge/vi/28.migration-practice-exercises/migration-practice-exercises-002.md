# Tái hiện trường hợp -source và -target vẫn gọi nhầm API mới

Trong **Java Advance Compatibility Migration**, một lỗi khó phát hiện là **JAR có bytecode tương thích với JDK cũ nhưng lại tham chiếu đến một API chỉ có ở JDK mới**. Ứng dụng có thể biên dịch hoàn toàn thành công với cặp tham số **-source** và **-target**, nhưng thất bại khi triển khai lên runtime được công bố hỗ trợ.

Đây là một **bài thực hành** thuộc chương **Bài thực hành**. Chúng ta sẽ chủ động tạo tình huống:

1. Dùng **javac của JDK 21** để biên dịch mã được khai báo là tương thích **Java 8**.
2. Chỉ định **-source 8 -target 8** nhưng cố tình gọi **String.isBlank()**, API chỉ xuất hiện từ **Java 11**.
3. Quan sát compiler có thể tạo class file **major version 52**.
4. Chạy class đó trên **Java 8** và thấy **NoSuchMethodError**.
5. Đổi sang **--release 8** để compiler phát hiện lỗi ngay ở thời điểm build.
6. Mở rộng bài học sang Gradle, Maven, thư viện bên thứ ba, CI matrix và kiểm thử runtime thật.

Điều cần nhớ trước khi bắt đầu: **ngôn ngữ nguồn, định dạng bytecode và tập API nền tảng là ba giới hạn khác nhau**. Hai cờ **-source** và **-target** không kiểm soát đầy đủ cả ba giới hạn.

> **Phạm vi thực hành:** Các lệnh bên dưới là hướng dẫn để người học chạy trên máy hoặc môi trường lab. Kết quả hiển thị là **kết quả kỳ vọng**, không phải tuyên bố đã thực thi trong bài viết này. Compiler messages có thể khác đôi chút theo JDK vendor và bản vá.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích khác biệt giữa **-source**, **-target** và **--release**.
- Tái hiện một artifact class-file Java 8 nhưng gọi API Java 11.
- Hiểu tại sao Java 8 có thể nạp class nhưng lỗi lúc liên kết lời gọi phương thức.
- Dùng **javap -verbose** và **javap -c** để quan sát bytecode.
- Dùng **--release 8** để chặn tham chiếu sai tới API chuẩn.
- Phân biệt lỗi **NoSuchMethodError**, **NoClassDefFoundError** và **UnsupportedClassVersionError**.
- Thiết kế kiểm thử độc lập giữa **compiler JDK**, **target release** và **runtime JDK**.
- Nhận ra giới hạn của **--release** đối với dependency và mã sinh.
- Chuyển kiến thức sang Gradle, Maven và CI release gates.

## 2. Ba trục tương thích mà developer thường nhầm

Giả sử dự án có yêu cầu **chạy được trên Java 8**, nhưng tổ chức muốn chuyển môi trường build sang JDK 21.

Có ít nhất ba câu hỏi độc lập:

| Trục | Câu hỏi | Công cụ |
|---|---|---|
| Ngôn ngữ nguồn | Có được viết cú pháp Java mới không? | **-source** hoặc phần source của **--release** |
| Bytecode | JVM cũ có đọc định dạng class file không? | **-target** hoặc phần target của **--release** |
| Java SE API | Các class/method của Java platform có tồn tại ở runtime cũ không? | **--release** khi compile bằng javac hỗ trợ |
| Runtime behavior | Code/dependency có hoạt động đúng trên JVM cũ không? | Test thực thi với JVM cũ |
| Dependency compatibility | JAR bên thứ ba có tương thích runtime tối thiểu không? | Dependency audit và runtime integration tests |

### 2.1. -source làm gì?

Ví dụ:

~~~bash
javac -source 8 ApiTrap.java
~~~

Tùy chọn **-source 8** yêu cầu compiler kiểm tra source theo cú pháp/ngữ nghĩa ngôn ngữ phù hợp Java 8 trong giới hạn javac hỗ trợ.

Nó không có nghĩa rằng compiler tự động dùng toàn bộ Java SE 8 API. Một lời gọi phương thức xuất hiện ở Java 11 vẫn có thể hợp lệ về **cú pháp Java 8**.

### 2.2. -target làm gì?

Ví dụ:

~~~bash
javac -target 8 ApiTrap.java
~~~

Tùy chọn **-target 8** yêu cầu compiler tạo class-file format phù hợp Java 8; trong ví dụ này là **major version 52**.

Một bytecode có thể có định dạng JVM cũ hiểu, nhưng symbol mà bytecode tham chiếu tới có thể không tồn tại trong API của runtime cũ.

### 2.3. --release làm gì?

Ví dụ:

~~~bash
javac --release 8 ApiTrap.java
~~~

Tùy chọn **--release 8**, được giới thiệu trong JDK 9 qua **JEP 247**, kết hợp kiểm tra source language, target bytecode và các **API Java platform** được phép sử dụng cho release được chọn.

Nó giúp tránh việc compile bằng JDK mới nhưng lỡ gọi API của JDK mới trong chương trình phải chạy trên JDK cũ.

### 2.4. Bảng so sánh

| Cấu hình khi chạy javac 21 | Syntax level | Class-file target | Hạn chế Java SE API theo Java 8? |
|---|---|---|---|
| **-source 8 -target 8** | Java 8 | Java 8 | **Không đầy đủ**; có thể thấy API JDK 21 |
| **--release 8** | Java 8 | Java 8 | **Có** với các API nền tảng được hỗ trợ |
| Không cấu hình | Mặc định theo javac 21 | Mặc định theo javac 21 | Không nhằm chạy trên Java 8 |

Điểm mấu chốt: **-source 8 -target 8 không phải cách viết khác của --release 8**.

## 3. Chuẩn bị môi trường lab

Bài thực hành chính dùng:

- **JDK 21** để chạy javac mới.
- **JDK/JRE 8** để chạy artifact trên runtime cũ.
- Một terminal.
- Một thư mục làm việc độc lập, ví dụ **java-api-trap-lab**.
- Không cần Maven, Gradle hay dependency bên ngoài ở phần đầu.

Có thể dùng JDK 17 hoặc một javac mới hơn hỗ trợ **--release 8** thay cho javac 21, miễn là bản đó có **String.isBlank()**.

### 3.1. Kiểm tra hai runtime

Trên máy có JDK 21 trong PATH:

~~~bash
java -version
javac -version
~~~

Kết quả mong đợi là version 21 cho compiler sẽ sử dụng. Trên máy có nhiều JDK, **java** và **javac** trong PATH không nhất thiết thuộc cùng một installation.

Để bảo đảm đúng compiler, dùng đường dẫn tuyệt đối, ví dụ trên Unix:

~~~bash
/opt/jdks/jdk-21/bin/javac -version
/opt/jdks/jdk8/bin/java -version
~~~

Các đường dẫn chỉ minh họa. Thay bằng nơi cài đặt JDK thật.

Windows PowerShell có thể dùng:

~~~powershell
& "C:\Java\jdk-21\bin\javac.exe" -version
& "C:\Java\jdk8\bin\java.exe" -version
~~~

Đây cũng là placeholder. **Không chạy cả hai lệnh chỉ bằng tên java/javac** nếu PATH thay đổi không kiểm soát được.

### 3.2. Khi không có Java 8 runtime

Có thể làm các bước compile và kiểm tra **javap** bằng JDK mới trước. Tuy nhiên, để quan sát **NoSuchMethodError trên runtime Java 8**, bắt buộc phải có một Java 8 runtime thật hoặc môi trường container/test image đáng tin cậy chứa Java 8.

Không được viết “đã tái hiện runtime error” chỉ từ việc compiler không cảnh báo.

### 3.3. Cấu trúc thư mục

~~~text
java-api-trap-lab/
  src/
    ApiTrap.java
  out/
    source-target/
    release/
~~~

Có thể tự tạo các thư mục hoặc dùng lệnh phù hợp hệ điều hành. Cần **output directories khác nhau** cho hai lần biên dịch để không nhầm class file cũ.

## 4. Viết source cố tình gọi API mới

Tạo file **src/ApiTrap.java**:

~~~java
public final class ApiTrap {
    public static void main(String[] args) {
        String input = "   ";

        // String.isBlank() chỉ có từ Java 11.
        boolean blank = input.isBlank();

        System.out.println("isBlank = " + blank);
    }
}
~~~

Đây là source cố ý có vấn đề khi phải chạy Java 8.

### 4.1. Vì sao cú pháp này hợp lệ theo Java 8?

- Class, main method và local variable đều dùng cú pháp Java 8.
- Gọi instance method bằng dấu chấm là cú pháp đã tồn tại từ lâu.
- Không có records, text blocks, switch expressions hay tính năng cú pháp mới.
- Điều khác biệt duy nhất là **API String.isBlank() không tồn tại trong Java 8**.

**String.isBlank()** được giới thiệu ở **Java 11**. Với javac 21, compiler nhìn thấy method này trong Java platform hiện tại, trừ khi được yêu cầu biên dịch theo API của release cũ bằng **--release**.

### 4.2. Vì sao chọn String.isBlank()?

Nó có ba ưu điểm cho lab:

1. Không cần dependency bên thứ ba.
2. Lời gọi đủ nhỏ để quan sát trong bytecode.
3. Khác biệt API rõ ràng: **Java 8 không có**, **Java 11+ có**.

Vì source dùng API mới nhưng không dùng syntax mới, nó minh họa đúng lỗ hổng của **-source/-target**.

## 5. Thí nghiệm A: javac mới với -source 8 -target 8

Dùng **javac 21**:

~~~bash
javac -source 8 -target 8 \
  -d out/source-target \
  src/ApiTrap.java
~~~

Trên Windows PowerShell có thể viết trên một dòng:

~~~powershell
& "C:\Java\jdk-21\bin\javac.exe" -source 8 -target 8 -d out\source-target src\ApiTrap.java
~~~

Nếu thư mục out/source-target chưa tồn tại, chuẩn bị nó trước theo shell. Javac có thể tạo package directories, nhưng việc tạo output root cho lab là cách dễ kiểm soát.

### 5.1. Kết quả kỳ vọng

Trên javac mới hỗ trợ các options này, **biên dịch có thể thành công**, dù source gọi API Java 11.

Compiler có thể đưa ra cảnh báo về cách sử dụng **-source/-target** hoặc yêu cầu boot class path, tùy phiên bản. **Cảnh báo không đồng nghĩa lỗi biên dịch.**

Kỳ vọng:

~~~text
Build result: SUCCESS
Generated: out/source-target/ApiTrap.class
Target class-file major version: 52
Referenced Java method: java.lang.String.isBlank()
~~~

Đây là kết quả kỳ vọng của thí nghiệm, không phải stdout chuẩn cố định của javac.

### 5.2. Vì sao compiler cho qua?

Javac đang thực hiện hai việc:

- Kiểm tra source có dùng syntax vượt Java 8 không.
- Sinh class file có định dạng bytecode Java 8.

Nhưng khi resolve **String.isBlank()**, compiler có thể nhìn vào API của **JDK 21 đang thực thi javac**, nơi method đó tồn tại.

Do đó javac biết cách sinh một lời gọi symbol có tên **java/lang/String.isBlank:()Z**, dù runtime Java 8 chưa hề định nghĩa symbol ấy.

### 5.3. Một cảnh báo dễ bị bỏ qua

Nếu compiler báo cảnh báo về boot class path khi dùng **-source 8**, đó chính là dấu hiệu cấu hình chưa khóa chặt Java 8 platform APIs. Không nên chỉ ẩn warning bằng **-Xlint:-options** rồi tuyên bố artifact hoàn toàn tương thích.

Biện pháp đúng cho compile cross-release hiện đại là **--release 8** và test runtime Java 8.

## 6. Thí nghiệm B: kiểm tra class-file version bằng javap

Dùng **javap** của JDK mới để kiểm tra artifact vừa biên dịch:

~~~bash
javap -verbose \
  -classpath out/source-target \
  ApiTrap
~~~

Tìm phần:

~~~text
major version: 52
~~~

**Major 52** tương ứng class-file format của Java 8.

### 6.1. Xem lệnh gọi API trong constant pool

Cũng trong output **javap -verbose**, có thể xuất hiện method reference tương đương:

~~~text
Methodref java/lang/String.isBlank:()Z
~~~

Cú pháp dòng và chỉ số constant-pool có thể thay đổi theo compiler.

Ý nghĩa:

- Owner class: **java/lang/String**.
- Method name: **isBlank**.
- Descriptor: **()Z**, tức không nhận đối số và trả về boolean.
- Bytecode đang tham chiếu một method mà runtime cần resolve.

### 6.2. Xem hướng dẫn bytecode

~~~bash
javap -c -p \
  -classpath out/source-target \
  ApiTrap
~~~

Kỳ vọng trong thân **main** có lệnh tương đương:

~~~text
invokevirtual java/lang/String.isBlank:()Z
~~~

Không cần memorise constant-pool index. Hãy chú ý **invokevirtual**, tên method và descriptor.

### 6.3. Kết luận tạm thời

Tại thời điểm này ta có:

- Class-file version Java 8.
- Source cú pháp Java 8.
- Symbol tham chiếu thuộc API Java 11.

**Đó là bằng chứng class-file version và Java API compatibility là hai trục độc lập.** Nhưng để chứng minh runtime Java 8 sẽ lỗi, ta cần bước tiếp theo.

## 7. Thí nghiệm C: chạy class file trên Java 8

Dùng **Java 8 runtime**, không phải Java 21:

~~~bash
/opt/jdks/jdk8/bin/java \
  -cp out/source-target \
  ApiTrap
~~~

Windows PowerShell:

~~~powershell
& "C:\Java\jdk8\bin\java.exe" -cp out\source-target ApiTrap
~~~

### 7.1. Kết quả kỳ vọng

Có thể thấy thông báo gần với:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  java.lang.String.isBlank()Z
    at ApiTrap.main(ApiTrap.java:...)
~~~

Message cụ thể, line number và cách JVM render method signature có thể khác. **Loại lỗi quan trọng là NoSuchMethodError** khi JVM cố thực thi lời gọi đến một method không tồn tại trong class **java.lang.String** của Java 8.

### 7.2. Vì sao không phải UnsupportedClassVersionError?

Vì class file là **major 52**, Java 8 có thể đọc định dạng này.

JVM không nhất thiết kiểm tra và resolve toàn bộ mọi method reference ngay lúc load class. Khi thực thi lời gọi **String.isBlank()**, JVM cần liên kết reference tới method thích hợp trong Java 8 platform class. Method không tồn tại, nên phát sinh lỗi linkage.

Nếu class file là major 65 từ Java 21, Java 8 có thể từ chối sớm bằng **UnsupportedClassVersionError**. Nhưng trong lab này, định dạng class hợp lệ; **API symbol** mới là vấn đề.

### 7.3. Vì sao chạy trên Java 21 lại thành công?

Thử cùng artifact bằng Java 21:

~~~bash
/opt/jdks/jdk-21/bin/java \
  -cp out/source-target \
  ApiTrap
~~~

Kết quả kỳ vọng:

~~~text
isBlank = true
~~~

Java 21 có method **String.isBlank()**, nên method reference resolve được. Đây không phải bằng chứng artifact tương thích Java 8; đó chỉ là bằng chứng nó chạy được trên Java 21.

## 8. Thí nghiệm D: dùng --release 8 để bắt lỗi lúc compile

Bây giờ biên dịch **cùng một source**, nhưng đổi options:

~~~bash
javac --release 8 \
  -d out/release \
  src/ApiTrap.java
~~~

Windows PowerShell:

~~~powershell
& "C:\Java\jdk-21\bin\javac.exe" --release 8 -d out\release src\ApiTrap.java
~~~

### 8.1. Kết quả kỳ vọng

Javac 21 có thể báo:

~~~text
error: cannot find symbol
        boolean blank = input.isBlank();
                             ^
  symbol:   method isBlank()
  location: variable input of type String
~~~

Kết quả mong muốn:

~~~text
Compile result: FAILURE (intended)
Reason: String.isBlank() is not part of Java 8 platform API.
No valid ApiTrap.class should be released from this attempt.
~~~

Đây là **một test thành công về kiểm soát tương thích**: lỗi được phát hiện trước khi phát hành thay vì đến lúc chạy trên máy khách.

### 8.2. --release tác động ở tầng API như thế nào?

Với **--release 8**, javac dùng thông tin về Java 8 platform APIs thay vì tự cho source nhìn toàn bộ Java platform API của JDK 21.

Vì **String.isBlank()** không thuộc Java 8 API, compiler không thể resolve lời gọi và báo lỗi.

### 8.3. Vì sao nên dùng --release thay cho mẹo sửa bootclasspath?

Trước đây có cách cấu hình **-bootclasspath** hoặc tương đương để biên dịch dựa trên classes của JDK cũ. Cách đó cần chuẩn bị đúng boot classes và có nhiều chi tiết dễ sai.

**--release** là cơ chế được JDK hỗ trợ để compile cho release cũ trong tập target được javac hiện tại hỗ trợ. Nó dễ review, đồng nhất hơn và chặn API platform mới hiệu quả hơn chỉ dùng **-source/-target**.

Không phải mọi javac đều hỗ trợ mọi release cũ; kiểm tra tài liệu của compiler target. Ví dụ, dùng **--release 8** với JDK 21 là một tình huống phổ biến được hỗ trợ.

## 9. Thí nghiệm E: sửa source để thật sự tương thích Java 8

Thay method **String.isBlank()** bằng logic chỉ sử dụng API Java 8:

~~~java
public final class ApiTrap {
    public static void main(String[] args) {
        String input = "   ";

        boolean blank = input.trim().isEmpty();

        System.out.println("isBlank = " + blank);
    }
}
~~~

Sau đó:

~~~bash
javac --release 8 \
  -d out/release \
  src/ApiTrap.java
~~~

Và chạy trên Java 8:

~~~bash
/opt/jdks/jdk8/bin/java \
  -cp out/release \
  ApiTrap
~~~

Kết quả kỳ vọng:

~~~text
isBlank = true
~~~

### 9.1. Cảnh báo về semantic compatibility

**trim().isEmpty() không tương đương tuyệt đối với String.isBlank() trong mọi trường hợp Unicode.**

- **String.trim()** xử lý một phạm vi ký tự whitespace theo semantics cũ.
- **String.isBlank()** dựa trên định nghĩa ký tự whitespace theo Java API mới hơn.
- Một số chuỗi Unicode có thể cho kết quả khác.

Đoạn thay thế trên chỉ phục vụ lab với chuỗi gồm các khoảng trắng ASCII. Trong sản phẩm thật, nếu phải giữ chính xác semantics của API mới, hãy viết hoặc dùng implementation tương đương được kiểm thử với bộ dữ liệu Unicode và support policy của dự án.

### 9.2. Khi nào không nên tự viết lại API?

Nếu feature mới có semantics phức tạp hoặc liên quan bảo mật/crypto, không nên thay bằng một helper sơ sài. Các phương án khác:

- Dùng thư viện được kiểm chứng còn hỗ trợ Java 8.
- Hoãn feature cho đến khi kết thúc hỗ trợ Java 8.
- Tách implementation theo runtime.
- Nâng minimum Java version có chủ đích và công bố breaking change.

Sửa lỗi compile không tự động bảo toàn hành vi nghiệp vụ.

## 10. Ma trận kết quả tổng hợp

| Cấu hình | Compile bằng JDK 21 | Class major | Chạy Java 8 | Chạy Java 21 |
|---|---|---:|---|---|
| Source gọi isBlank, **-source 8 -target 8** | Có thể thành công | 52 | **NoSuchMethodError** | Thành công |
| Source gọi isBlank, **--release 8** | **Thất bại có chủ đích** | Không phát hành | Không áp dụng | Không áp dụng |
| Source dùng trim().isEmpty(), **--release 8** | Thành công | 52 | Thành công với input demo | Thành công |
| Source gọi isBlank, compile mặc định JDK 21 | Thành công | 65 | **UnsupportedClassVersionError** | Thành công |

Bảng phân biệt hai lỗi mà nhiều người gộp chung thành “không tương thích Java 8”:

- **Bytecode quá mới:** JVM không nạp được class format.
- **API quá mới:** JVM có thể nạp class format, nhưng không resolve được symbol.

## 11. Đào sâu: cơ chế liên kết (linking) ở JVM

Trong class file, lời gọi không chứa mã của **String.isBlank()**. Nó chứa symbolic reference đến method thuộc một class cụ thể.

Một biểu diễn đơn giản:

~~~text
ApiTrap.class
  major version = 52
  constant pool:
    java/lang/String
    isBlank
    ()Z
  code:
    invokevirtual ... java/lang/String.isBlank:()Z
          |
          v
Java 8 runtime java.lang.String
          |
          +--> No method named isBlank()Z
          |
          v
NoSuchMethodError
~~~

Class file vẫn hợp lệ ở mức format. Lỗi xuất hiện khi JVM phải resolve reference tới API chưa có.

### 11.1. Các giai đoạn ở mức khái niệm

- **Loading:** tìm/đọc class.
- **Verification:** kiểm tra cấu trúc bytecode và các ràng buộc liên quan.
- **Preparation:** chuẩn bị static fields và trạng thái cần thiết.
- **Resolution:** ánh xạ symbolic references tới entities thực.
- **Initialization:** chạy class initialization khi cần.

Thời điểm resolution cụ thể có thể được thực hiện sớm hoặc trễ theo JVM specification. Điều không thay đổi là một method reference không tồn tại có thể gây **NoSuchMethodError** khi cần dùng.

### 11.2. NoSuchMethodError khác NoClassDefFoundError

Nếu source gọi một **method mới trên class cũ** như **String.isBlank()**, Java 8 vẫn có **java.lang.String**, nhưng không có method đó. Hướng lỗi điển hình là **NoSuchMethodError**.

Nếu source tham chiếu trực tiếp đến **class chỉ có ở JDK mới**, runtime cũ có thể gặp **NoClassDefFoundError** hoặc **ClassNotFoundException** tùy cách tìm/nạp.

Ví dụ **java.util.HexFormat** chỉ có từ Java 17; một ứng dụng target Java 11 nhưng được compile sai bằng JDK mới có thể vấp vấn đề khi nạp/sử dụng class này trên Java 11.

### 11.3. UnsupportedClassVersionError khác hai lỗi trên

Nếu compiler xuất class file vượt quá major version JVM runtime hỗ trợ, JVM có thể từ chối class trước khi tới lời gọi API.

Để điều tra đúng, trước tiên kiểm tra **class major version**, sau đó kiểm tra **method/class references** và runtime classpath.

## 12. Bài tập bổ sung: API mới của Collection

Tạo file **ListTrap.java**:

~~~java
import java.util.List;

public final class ListTrap {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");
        System.out.println(names);
    }
}
~~~

**List.of()** được giới thiệu từ Java 9. Nó không có trong Java 8.

### 12.1. Thử compile với source/target

~~~bash
javac -source 8 -target 8 \
  -d out/source-target \
  src/ListTrap.java
~~~

Javac 21 có thể compile vì JDK 21 cung cấp **List.of()**, còn cú pháp lời gọi vẫn tương thích Java 8.

### 12.2. Chạy trên Java 8

~~~bash
/opt/jdks/jdk8/bin/java \
  -cp out/source-target \
  ListTrap
~~~

Kỳ vọng có thể là **NoSuchMethodError** cho **java.util.List.of(...)**.

### 12.3. Đổi sang --release 8

~~~bash
javac --release 8 \
  -d out/release \
  src/ListTrap.java
~~~

Kỳ vọng compiler báo không tìm thấy **List.of()** trong Java 8 API.

### 12.4. Sửa có chủ đích

Một bản tương thích Java 8:

~~~java
import java.util.Arrays;
import java.util.List;

public final class ListTrap {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh");
        System.out.println(names);
    }
}
~~~

**Lưu ý:** **Arrays.asList** và **List.of** có semantics khác nhau. List.of tạo list không cho thay đổi nội dung và không chấp nhận null; Arrays.asList tạo fixed-size list được backing bởi array, cho phép thay phần tử bằng **set** và có thể chứa null. Nếu business code dựa vào immutability hoặc null rejection, cần chọn cách thay thế có semantics đúng, không chỉ chọn API cũ có tên gần giống.

## 13. Bài tập bổ sung: khi baseline là Java 11

Trong nhiều dự án hiện đại, baseline không phải Java 8 mà là Java 11.

Một ví dụ:

~~~java
public final class ApiTrap11 {
    public static void main(String[] args) {
        String message = "Hello %s".formatted("migration");
        System.out.println(message);
    }
}
~~~

**String.formatted()** xuất hiện từ Java 15, không có trong Java 11.

Thử bằng javac 21:

~~~bash
javac -source 11 -target 11 \
  -d out/source-target \
  src/ApiTrap11.java
~~~

Kỳ vọng có thể compile thành class-file **major 55**, nhưng chạy trên Java 11 sẽ gặp lỗi thiếu method.

Dùng:

~~~bash
javac --release 11 \
  -d out/release \
  src/ApiTrap11.java
~~~

Kỳ vọng compiler phát hiện lời gọi **formatted** không thuộc Java 11 API.

### 13.1. Vì sao thêm bài tập Java 11?

Nó chứng minh vấn đề không chỉ liên quan Java 8. **Mọi migration compile trên JDK mới để hỗ trợ runtime cũ** đều cần phân biệt:

- Source/language target.
- Bytecode target.
- Java SE API target.
- Runtime thực thi.

## 14. Thí nghiệm phụ: source syntax vượt release

Để thấy **-source** bảo vệ ngôn ngữ như thế nào, tạo file:

~~~java
public record Point(int x, int y) {
}
~~~

Record là tính năng ngôn ngữ chuẩn từ Java 16.

Nếu dùng:

~~~bash
javac -source 8 -target 8 \
  -d out/source-target \
  src/Point.java
~~~

Compiler sẽ từ chối cú pháp record vì **-source 8**.

Điều này làm rõ sự khác biệt:

- **Tính năng cú pháp mới**: thường bị **-source** chặn.
- **Lời gọi API mới bằng cú pháp cũ**: có thể lọt qua **-source/-target**.
- **--release**: giúp chặn cả lời gọi API Java platform vượt release.

Không kết luận **-source/-target vô tác dụng**; chúng làm đúng nhiệm vụ của mình nhưng không đầy đủ cho mục tiêu tương thích runtime.

## 15. Vì sao dùng -bootclasspath từng phổ biến?

Trong các hệ thống build cũ, developer có thể chỉ định bootclasspath gồm classes của JDK đích để tránh compiler nhìn thấy API mới.

Mô hình cũ:

~~~text
javac mới
   |
   +--> -source 8
   +--> -target 8
   +--> bootclasspath Java 8
   |
   v
Hạn chế API nhìn thấy
~~~

Tuy nhiên cách này có những vấn đề:

- Cần chuẩn bị boot classes JDK cũ chính xác.
- Dễ sai khi chọn path hoặc modules.
- Không thuận tiện cho JDK 9+ platform module system.
- Có thể bị cấu hình khác nhau giữa local và CI.
- Cần phân biệt Java 8 **rt.jar** với các modular JDK mới.

**--release** được thiết kế để giải quyết cross-compilation theo platform release thuận tiện hơn. Không lạm dụng bootclasspath hay sửa thủ công JDK installation khi javac hỗ trợ **--release**.

## 16. Gradle: thay sourceCompatibility/targetCompatibility bằng options.release

Giả sử **build.gradle** có:

~~~groovy
plugins {
    id 'java'
}

sourceCompatibility = JavaVersion.VERSION_1_8
targetCompatibility = JavaVersion.VERSION_1_8
~~~

Nếu Gradle thực thi **javac 21** và không cấu hình **--release**, việc đặt source/target ở Java 8 không bảo đảm chặn API Java 11 như **String.isBlank()**.

### 16.1. Cấu hình khuyến nghị cho target Java 8

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
}
~~~

Ý nghĩa:

- Compile bằng toolchain JDK 21.
- Hạn chế syntax, bytecode và Java platform API của source target Java 8.
- Kiểm tra lời gọi **String.isBlank()** ngay ở compile time.

**Cần dùng Gradle version còn hỗ trợ cấu hình JDK và target release tương ứng.** Không suy luận rằng mọi Gradle release có thể chạy daemon/test tasks trên cả Java 8 và Java 21.

### 16.2. Gradle Kotlin DSL

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(8)
}
~~~

Chọn Groovy hoặc Kotlin DSL theo project; không cần duy trì cả hai.

### 16.3. Build với --release chưa đủ cho runtime tests

Gradle có thể biên dịch target Java 8 bằng JDK 21 nhưng chạy **Test** task trên Java 21. Khi đó một JAR dependency chỉ chạy Java 21 vẫn có thể không bị phát hiện.

Cần ít nhất một **Java 8 runtime smoke/integration test** cho artifact được phát hành nếu Java 8 nằm trong support policy.

### 16.4. Không dùng test JVM quá cũ với tool không hỗ trợ

Các Gradle/Test/coverage plugin versions mới có thể có minimum Java version cao. Nếu cấu hình test launcher Java 8 không được stack hiện tại hỗ trợ, hãy tách một runtime smoke job chạy artifact bằng Java 8 hoặc chọn tool versions theo support policy.

Không đặt một test lane màu xanh nhờ việc bỏ qua toàn bộ test thực thi trên Java 8.

## 17. Maven: dùng maven.compiler.release

Với Maven Compiler Plugin hiện đại có hỗ trợ **release**:

~~~xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>8</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Version trong ví dụ chỉ minh họa cú pháp. Với dự án thật, cần kiểm tra Maven Compiler Plugin, JDK và Maven runtime compatibility.

### 17.1. Cấu hình có thể gây hiểu nhầm

~~~xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
</properties>
~~~

Nếu javac thực tế là JDK mới, hai thuộc tính này không có cùng ý nghĩa API compatibility như **release**.

### 17.2. Maven Toolchains

Nếu Maven process chạy bằng JDK 21 nhưng compiler được chọn bằng JDK 8, javac 8 đương nhiên biên dịch dựa trên Java 8 API. Tuy nhiên, đó là một thiết kế toolchain khác với **javac 21 --release 8**.

Cần ghi rõ:

- Maven chạy trên JDK nào.
- Compiler thực tế là javac nào.
- **release** target là gì.
- Test executor sử dụng JDK nào.
- Các plugins/annotation processors chạy ở JVM nào.
- Artifact cuối được test trên runtime nào.

Maven Compiler Plugin và test plugins có mức hỗ trợ toolchain riêng; không giả định toolchain compiler tự điều khiển tất cả Maven goals.

## 18. Giới hạn quan trọng: --release không kiểm tra toàn bộ thư viện bên thứ ba

**--release 8** rất hữu ích để hạn chế **Java platform APIs** theo Java 8. Nhưng nó không phải một bộ kiểm chứng toàn bộ dependency graph.

Ví dụ:

~~~text
Application --release 8
       |
       +--> LegacyCompatibleLibrary.class (major 52)
                     |
                     +--> gọi String.isBlank() (Java 11)
~~~

Giả sử một thư viện đã bị biên dịch sai với **-source 8 -target 8**, giống thí nghiệm đầu tiên. Ứng dụng tham chiếu API công khai của thư viện này nhưng không gọi **String.isBlank()** trực tiếp trong source ứng dụng.

### 18.1. Lỗi vẫn lọt qua được như thế nào?

Source ứng dụng:

~~~java
public final class App {
    public static void main(String[] args) {
        System.out.println(LegacyCompatibleLibrary.isInputBlank("  "));
    }
}
~~~

Source thư viện:

~~~java
public final class LegacyCompatibleLibrary {
    public static boolean isInputBlank(String value) {
        return value.isBlank();
    }
}
~~~

Nếu thư viện được compile trước đó bằng **javac 21 -source 8 -target 8** thành class major 52, rồi ứng dụng compile với **--release 8** và classpath chứa thư viện:

- Source ứng dụng chỉ gọi method của thư viện.
- Thư viện class file có định dạng Java 8.
- Compiler ứng dụng không nhất thiết phân tích lại toàn bộ thân method của dependency.
- Java 8 runtime vẫn có thể lỗi khi thực thi code thư viện.

**--release không tự sửa bytecode hoặc dependency đã được build sai.**

### 18.2. Cách khắc phục

- Xác nhận minimum Java của dependencies từ vendor.
- Đánh giá bytecode version của các JAR.
- Kiểm tra transitive dependencies và shaded JAR.
- Chạy integration/smoke tests trên runtime cũ thật.
- Dùng dependency validation/SBOM và build reproducibility.
- Khi thư viện nằm trong quyền kiểm soát, build nó bằng **--release** phù hợp.
- Đừng phát hành artifact chỉ dựa trên class-file major.

### 18.3. Class major không thể chứng minh mọi API reference

Một tool chỉ xem tất cả class major <= 52 sẽ bỏ sót **String.isBlank()** trong class major 52. Đó là chính vấn đề của bài thực hành.

Cần phân biệt:

- Class-file version scanner: phát hiện bytecode quá mới.
- Java platform API compatibility checker: phát hiện API platform quá mới.
- Runtime integration test: kiểm tra behavior/dependencies.
- Public API diff tool: kiểm tra interface công bố của một library.

Các công cụ này bổ sung cho nhau chứ không đồng nghĩa.

## 19. Các trường hợp --release vẫn không đủ để bảo đảm runtime

Ngoài dependencies đã compile sai, còn nhiều nguồn lỗi:

### 19.1. Reflection và dynamic invocation

Source có thể dùng:

~~~java
Class.forName("java.util.HexFormat");
~~~

Đây là lời gọi **Class.forName** vốn tồn tại từ lâu, còn tên class là một chuỗi. Compiler với **--release 8** không kiểm tra class thực sự có tồn tại tại runtime hay không chỉ từ chuỗi.

Nếu runtime Java 8 không có **java.util.HexFormat**, lỗi có thể xuất hiện khi chạy.

### 19.2. ServiceLoader và cấu hình resources

Một service provider class có thể chỉ tồn tại hoặc chỉ chạy trên JDK mới. Compiler không nhất thiết phát hiện trước mọi lỗi xảy ra khi load provider theo tên từ **META-INF/services**.

### 19.3. JNI và native code

JNI/native libraries có thể không hỗ trợ OS/architecture/JDK mục tiêu. Bytecode target hợp lệ không giải quyết binary dependencies.

### 19.4. Java agents và instrumentation

Byte Buddy, Mockito, JaCoCo, APM agents hoặc bytecode libraries có thể cần phiên bản hỗ trợ compiler/runtime mới. Những lỗi này là tool/runtime compatibility, không chỉ platform API compatibility.

### 19.5. JDK behavior và security policy

TLS, truststores, GC, locale, charset, timezone hoặc reflection policies có thể thay đổi giữa JDKs, dù code dùng API có từ lâu.

### 19.6. Multi-release JAR

Cùng một JAR có thể có class variants dưới **META-INF/versions/**. Runtime cũ và mới có thể chọn implementations khác nhau. Cần test từng runtime thật.

**Kết luận phần này:** **--release** giúp chặn một lớp sai sót compile-time quan trọng, nhưng không thay runtime test và integration test.

## 20. Dùng javap và các công cụ kiểm tra một cách đúng mục đích

### 20.1. javap -verbose

Dùng để xem major class-file version, constant pool, method references.

~~~bash
javap -verbose -classpath out/source-target ApiTrap
~~~

### 20.2. javap -c

Dùng để xem bytecode instructions, ví dụ **invokevirtual String.isBlank()**.

~~~bash
javap -c -classpath out/source-target ApiTrap
~~~

### 20.3. jdeps

**jdeps** hỗ trợ phân tích static dependencies và phát hiện nhiều trường hợp phụ thuộc vào JDK internal APIs, ví dụ với tùy chọn phù hợp như **--jdk-internals**.

Tuy nhiên, **không được coi một kết quả jdeps không có cảnh báo là bằng chứng mọi lời gọi Java platform API đều thuộc Java 8**. Static dependency analysis và API-release signature validation là hai loại kiểm tra khác nhau.

### 20.4. Animal Sniffer và các API compatibility checkers

Một số dự án dùng **Animal Sniffer** hoặc công cụ kiểm tra chữ ký API để bảo vệ target runtime, đặc biệt trong build systems có yêu cầu riêng.

Nếu đã dùng **--release** với JDK hỗ trợ, nó thường là cơ chế nền tảng thuận tiện nhất cho Java SE platform APIs; công cụ bổ sung có thể hữu ích để kiểm soát API ngoài nền tảng, kiểm tra thư viện hoặc policy dự án.

### 20.5. Đừng kiểm chứng chỉ bằng thông báo Build SUCCESS

Một build có thể thành công vì:

- Tests chạy trên JDK mới, không phải baseline.
- Generated class còn stale.
- Dependencies transitively được thay trong local cache.
- Code lỗi chưa được test.
- Build không thực sự sử dụng compiler được khai báo.

Hãy thu evidence: compiler version, flags, class major, API references và runtime test.

## 21. Thiết kế CI để không tái phạm lỗi

Một pipeline dành cho dự án phải hỗ trợ Java 8 có thể tách:

~~~text
Source commit
      |
      +--> Compile bằng javac 21 --release 8
      |          |
      |          +--> Block platform APIs mới
      |
      +--> Package artifact
      |
      +--> Runtime smoke trên Java 8
      |          |
      |          +--> Chạy dependency thật
      |
      +--> Runtime smoke trên Java 21
      |          |
      |          +--> Kiểm tra behavior trên target JDK
      |
      +--> Integration tests + security tests
      |
      v
Release gate
~~~

### 21.1. Vì sao cần cả old và new runtime?

- Java 8 runtime phát hiện API/dependency không tương thích baseline.
- Java 21 runtime phát hiện behavior/framework/agent không tương thích target.
- Cả hai giúp bảo vệ giai đoạn rolling deployment khi hai JDK cùng được hỗ trợ.

### 21.2. Một artifact hay hai artifact?

Nếu phát hành một artifact Java 8 target, cần kiểm tra chính artifact ấy trên cả hai runtimes.

Nếu phát hành hai variants, cần kiểm thử theo variant và đặt identity rõ ràng. Không để CI publish artifact theo job hoàn tất cuối cùng mà làm thay đổi nội dung ở cùng coordinates.

### 21.3. Giữ output directories độc lập

Tách build workspace hoặc output theo CI job. Không chạy cùng lúc javac 8 và javac 21 ghi vào một directory chung rồi kiểm tra một file class có thể bị ghi đè.

### 21.4. Dùng clean build

Generated sources hoặc stale class files có thể che lỗi compile. Ít nhất release verification phải có đường đi clean, tái lập được, không phụ thuộc output cũ.

## 22. Gợi ý bài kiểm thử tự động cho chính thí nghiệm

Bộ test bài học có thể gồm hai loại:

**Expected failure — API quá mới với --release 8:**

~~~text
Input: ApiTrap.java with String.isBlank()
Compiler: javac 21
Flags: --release 8
Expected: compilation fails
Reason: Java 8 API does not include isBlank()
~~~

**Expected runtime failure — build sai với -source/-target:**

~~~text
Input: ApiTrap.java with String.isBlank()
Compiler: javac 21
Flags: -source 8 -target 8
Expected compile: may succeed
Expected class major: 52
Runtime: Java 8
Expected runtime: NoSuchMethodError
~~~

**Expected success — source sửa và --release 8:**

~~~text
Input: ApiTrap.java with Java 8-compatible implementation
Compiler: javac 21
Flags: --release 8
Expected compile: success
Expected class major: 52
Runtime Java 8: success
Runtime Java 21: success
~~~

### 22.1. Không cần assert exact compiler warning

Warning text có thể khác theo JDK vendor và bản vá. Kiểm thử nên tập trung exit code, có/không có artifact hợp lệ, class major và runtime behavior.

### 22.2. Không cần assert exact NoSuchMethodError message

Tên method và loại lỗi quan trọng; cách render message/stack trace có thể khác. Nếu biến thí nghiệm thành test programmatic, phân biệt **NoSuchMethodError** với **UnsupportedClassVersionError** thay vì kiểm tra nguyên văn string.

### 22.3. Đường test phải thực sự dùng Java 8

Trên CI, việc chọn một JDK trong PATH có thể bị build tool override bằng toolchain. Với smoke test, dùng executable **java** có đường dẫn/launcher xác định và ghi lại version ngay trong test job.

## 23. Một câu hỏi khó: dùng javac 8 có giải quyết được không?

Nếu dùng chính **javac 8** để compile:

~~~text
javac 8 -source 8 -target 8
~~~

thì compiler nhìn thấy Java 8 platform APIs, nên source gọi **String.isBlank()** sẽ không compile.

Tuy nhiên, có các đánh đổi:

- CI phải tiếp tục duy trì JDK 8 compiler trong khi JDK 8 có thể nằm ngoài chính sách bảo trì của dự án.
- Build tool mới có thể không chạy trên JDK 8.
- Annotation processors có thể yêu cầu JDK mới.
- Cần đánh giá security support của JDK baseline.
- Test trên compiler cũ không thay thế test trên compiler target.

Nếu javac mới hỗ trợ **--release 8**, việc dùng javac mới với release target là một cách hữu ích để giữ API/language compatibility. Tuy nhiên vẫn cần test runtime cũ nếu tổ chức cam kết hỗ trợ nó.

## 24. Một câu hỏi khó khác: --release 8 có ngăn JDK internals không?

**--release** chủ yếu cho phép sử dụng các API của platform release tương ứng đã được định nghĩa cho compile. Nó cũng hạn chế việc dựa vào các JDK-specific internals vốn không thuộc API được phê duyệt.

Vì vậy, một codebase trước đây gọi **sun.misc.*** hoặc **com.sun.*** có thể gặp lỗi compile khi chuyển sang **--release**, dù code đó từng build với **-source/-target**.

Đây có thể là tín hiệu rằng dự án phụ thuộc API nội bộ, không nhất thiết là bug của --release. Hướng xử lý:

- Tìm API Java SE/JDK được hỗ trợ thay thế.
- Nâng library/framework phụ thuộc internal APIs.
- Đánh giá reflection/module compatibility.
- Nếu cần runtime-specific implementation, cô lập và kiểm thử rõ.
- Không lạm dụng **--add-exports** hoặc **--add-opens** như một cách né mọi kiểm tra.

Một số flags mở module và **--release** có các ràng buộc riêng trên javac hiện đại; đọc javac documentation theo JDK thực tế.

## 25. Tương thích Java API không phải tương thích thư viện

Phân biệt:

| Nguồn API | --release 8 có bảo vệ toàn bộ? | Cần thêm gì? |
|---|---|---|
| Java SE 8 APIs được javac hỗ trợ | Có, trong phạm vi target release | Runtime test |
| Java SE APIs xuất hiện sau Java 8 | Chặn lời gọi trực tiếp trong source | Compile test |
| Thư viện thứ ba đã compile bằng major 52 nhưng gọi Java 11 API | Không tự phân tích lại body thư viện | Runtime/integration tests |
| Thư viện major 65 được đưa vào runtime | Không đảm bảo mọi đường classpath | Dependency audit/runtime |
| Reflection gọi tên class/method dạng String | Không thể kiểm tra đầy đủ tĩnh | Runtime test |
| Java agents/JNI | Không | Compatibility matrix |
| Khác biệt cấu hình TLS/GC/locale | Không | Regression tests theo runtime |
| Generated source | Có nếu generated source thực sự được compile với --release | Processor output/runtime tests |

Một bài thực hành đúng không nên kết thúc ở câu “cứ thêm --release là xong tất cả”. **--release** giải quyết bài toán API JDK nền tảng ở lúc compile, còn tương thích hệ thống cần thêm những bằng chứng khác.

## 26. Tình huống thực tế: SDK build Java 17 nhưng hỗ trợ Java 11

Giả sử một SDK công bố **minimum Java 11**. Nhóm chuyển compiler lên JDK 17, giữ:

~~~text
-source 11
-target 11
~~~

Một developer dùng **java.util.HexFormat**, API xuất hiện từ Java 17, trong implementation của SDK.

Compiler JDK 17 có thể chấp nhận cú pháp và thấy HexFormat. Artifact class version vẫn target Java 11, nhưng khi consumer chạy trên Java 11, class **java.util.HexFormat** không tồn tại.

Hướng lỗi phụ thuộc cách class được load và method được gọi; có thể liên quan **NoClassDefFoundError** hoặc class resolution failure, khác với **String.isBlank()** là method mới trên class cũ.

Nếu compiler SDK dùng **--release 11**, tham chiếu trực tiếp tới HexFormat sẽ bị phát hiện lúc compile.

Bài học: Khi thấy **UnsupportedClassVersionError**, kiểm tra class major; khi thấy **NoSuchMethodError/NoClassDefFoundError**, kiểm tra API/platform class availability và runtime dependency graph.

## 27. Câu hỏi ôn tập

### Câu 1

Một class có **major version 52** có chắc chạy đúng trên Java 8 không?

**Đáp án:** Không. Java 8 hiểu định dạng bytecode 52 nhưng class có thể tham chiếu API mới hơn hoặc dependency không tương thích.

### Câu 2

**-source 8** có chặn lời gọi **String.isBlank()** khi compiler là JDK 21 không?

**Đáp án:** Không nhất thiết. Lời gọi có cú pháp Java 8; nếu compiler nhìn thấy Java 21 platform API, nó có thể compile.

### Câu 3

**-target 8** kiểm soát điều gì?

**Đáp án:** Class-file target format, không đủ để giới hạn mọi method thuộc Java 8 platform API.

### Câu 4

**--release 8** phát hiện lỗi nào của bài lab?

**Đáp án:** Lời gọi trực tiếp đến **String.isBlank()**, method không thuộc Java 8 API.

### Câu 5

Vì sao Java 8 runtime có thể phát sinh **NoSuchMethodError** thay vì **UnsupportedClassVersionError**?

**Đáp án:** Class-file version đã là Java 8 (major 52), nhưng method reference trỏ tới API chưa tồn tại trong Java 8.

### Câu 6

Chỉ có **--release 8** thì có đủ để bảo vệ toàn bộ transitive dependencies không?

**Đáp án:** Không. Nó không tự phân tích toàn bộ body của JAR đã biên dịch trước, reflection hoặc native dependencies. Cần runtime tests và dependency analysis.

### Câu 7

Có nên thay **String.isBlank()** bằng **trim().isEmpty()** trong mọi ứng dụng không?

**Đáp án:** Không. Hai cách có thể khác nhau ở một số Unicode whitespace; cần kiểm tra semantics trước khi thay.

### Câu 8

CI biên dịch target Java 8 bằng javac 21 và chạy unit tests trên Java 21 có chứng minh Java 8 compatibility không?

**Đáp án:** Không. Phải chạy artifact trên Java 8 runtime thật hoặc có bằng chứng tương ứng cho những rủi ro runtime còn lại.

## 28. Lỗi thường gặp khi làm lab

### 28.1. Vô tình dùng Java 21 để chạy thí nghiệm runtime Java 8

**Triệu chứng:** Chương trình in **isBlank = true**, không có lỗi.

**Giải pháp:** kiểm tra đường dẫn **java** executable và **java -version** trong đúng terminal/job.

### 28.2. Không tạo output directories riêng

**Triệu chứng:** Biên dịch **--release 8** thất bại nhưng vẫn thấy class file cũ trong thư mục output.

**Giải pháp:** dùng **out/source-target** và **out/release** riêng, dọn đúng build-owned output nếu cần.

### 28.3. Xem cảnh báo là lỗi chính

**Triệu chứng:** Warning về bootclasspath hoặc source option khiến người học tưởng compile đã bị chặn.

**Giải pháp:** kiểm tra exit code và class file; phân biệt warning với lỗi compile.

### 28.4. Chạy javap trên source thay vì class đúng

**Triệu chứng:** Không thấy major version hoặc method reference.

**Giải pháp:** chỉ định classpath tới thư mục output vừa compile.

### 28.5. Dùng javac 8 thay cho javac 21

**Triệu chứng:** Source gọi isBlank bị từ chối ngay với -source 8 -target 8.

**Giải pháp:** đây là hành vi bình thường vì javac 8 không thấy String.isBlank. Lab chính yêu cầu **javac mới** để cho thấy lỗ hổng.

### 28.6. Chạy thí nghiệm trên JDK không còn hỗ trợ -source 8

**Triệu chứng:** Compiler từ chối option release cũ.

**Giải pháp:** kiểm tra javac documentation và chọn cặp target/compiler được hỗ trợ; ví dụ minh họa dùng JDK 21.

### 28.7. Coi -Xlint:-options là cách khắc phục

**Triệu chứng:** Warning biến mất, artifact vẫn lỗi Java 8.

**Giải pháp:** dùng **--release 8**, không chỉ ẩn cảnh báo.

### 28.8. Thay API bằng helper có semantics khác

**Triệu chứng:** Tests ASCII xanh nhưng dữ liệu Unicode/production khác.

**Giải pháp:** kiểm tra behavior, edge cases và contract trước khi sửa.

### 28.9. Tin rằng một scanner major version đã hoàn thành kiểm tra

**Triệu chứng:** Tất cả classes major 52 nhưng Java 8 vẫn lỗi.

**Giải pháp:** kiểm tra method references và test runtime thật.

### 28.10. Quên dependencies hoặc generated code

**Triệu chứng:** Source chính --release 8 nhưng app vẫn lỗi do library/processor output.

**Giải pháp:** kiểm tra full artifact, dependencies và test runtime.

## 29. Checklist thực hành có thể sao chép

### Chuẩn bị

- [ ] Có javac JDK 21 hoặc JDK mới hỗ trợ --release 8.
- [ ] Có Java 8 runtime thực để chạy thí nghiệm.
- [ ] Kiểm tra version hai executables.
- [ ] Tạo source ApiTrap.java với String.isBlank().
- [ ] Tách output directories của các lần compile.

### Thí nghiệm -source/-target

- [ ] Chạy javac 21 -source 8 -target 8.
- [ ] Ghi exit code và cảnh báo nếu có.
- [ ] Xem class-file major 52 bằng javap.
- [ ] Xem method reference String.isBlank() bằng javap.
- [ ] Chạy artifact bằng Java 8.
- [ ] Ghi nhận NoSuchMethodError.
- [ ] Chạy lại bằng Java 21 để so sánh.

### Thí nghiệm --release

- [ ] Chạy javac 21 --release 8 với source gốc.
- [ ] Xác nhận compile từ chối method API mới.
- [ ] Sửa source bằng phương án Java 8-compatible phù hợp.
- [ ] Compile --release 8 thành công.
- [ ] Chạy artifact trên Java 8.
- [ ] Chạy trên Java 21 nếu support policy yêu cầu.

### Ứng dụng vào dự án

- [ ] Gradle/Maven có release target phù hợp.
- [ ] Build JVM/compiler JDK được ghi rõ.
- [ ] Có runtime smoke test trên JDK tối thiểu.
- [ ] Dependencies được kiểm tra Java compatibility.
- [ ] Annotation processors/generated code được kiểm tra.
- [ ] Không có stale output/cache che lỗi.
- [ ] CI matrix và release gate phù hợp support policy.
- [ ] Public minimum Java version được công bố đúng.

## 30. Mẫu ghi kết quả lab

~~~text
Lab ID: SOURCE_TARGET_API_TRAP
Application source:
Compiler vendor/version:
Compile flags A: -source 8 -target 8
A compile exit code:
A warning count:
A class major version:
A referenced API:
A runtime Java 8 result:
A runtime Java 21 result:

Compile flags B: --release 8
B compile exit code:
B compiler diagnosis:

After source fix:
Compile flags: --release 8
Class major:
Runtime Java 8:
Runtime Java 21:
Dependency/runtime notes:
Evidence paths:
Conclusion:
~~~

Một bản ghi có compiler version, classfile version, method reference và runtime outcome là bằng chứng tốt hơn chỉ ghi “lệnh chạy thành công”.

## 31. Tài liệu tham khảo

Nên đối chiếu theo JDK/compiler đang sử dụng:

- **JEP 247 — Compile for Older Platform Versions:** https://openjdk.org/jeps/247
- **javac command (JDK 21):** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Java 21 Virtual Machine Specification, class-file format:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **JVM Specification — Loading, Linking and Initializing:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
- **String API, Java 8:** https://docs.oracle.com/javase/8/docs/api/java/lang/String.html
- **String API, Java 11:** https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html
- **List API, Java 8:** https://docs.oracle.com/javase/8/docs/api/java/util/List.html
- **Gradle Java Toolchains:** https://docs.gradle.org/current/userguide/toolchains.html
- **Gradle JavaCompile options.release:** https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html
- **Maven Compiler Plugin:** https://maven.apache.org/plugins/maven-compiler-plugin/
- **Maven Compiler Plugin — Set --release:** https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html
- **Animal Sniffer Maven Plugin:** https://www.mojohaus.org/animal-sniffer/animal-sniffer-maven-plugin/

Những ví dụ về stdout, line number và warning được trình bày theo hành vi kỳ vọng của compiler/runtime, không phải output cố định trên mọi JDK vendor.

---

**Kết luận:** Hai cờ **-source 8 -target 8** có thể tạo class file **major 52** nhưng vẫn để code gọi **String.isBlank()**, method chỉ tồn tại từ Java 11. Java 8 đọc được class format nhưng không tìm thấy method khi liên kết lời gọi, dẫn đến **NoSuchMethodError**. Đổi sang **--release 8** làm javac phát hiện lời gọi API platform quá mới ngay lúc compile. Với migration thật, hãy kết hợp **--release**, kiểm tra dependency/generated code và **runtime test trên JDK tối thiểu**. Bảo đảm bytecode cũ là điều kiện cần, không phải bằng chứng đầy đủ của tương thích Java.
