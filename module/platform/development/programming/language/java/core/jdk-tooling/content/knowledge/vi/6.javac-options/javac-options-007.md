# Parameter metadata trong Java và tùy chọn `javac -parameters`

## 1. Parameter metadata là gì?

Parameter metadata là thông tin tên tham số hình thức của phương thức và constructor được lưu trong tệp bytecode `.class`. Thông tin này cho phép chương trình đọc tên tham số lúc chạy thông qua Java Reflection, thay vì chỉ biết kiểu và vị trí của từng tham số.

Ví dụ, với khai báo:

~~~java
public void createUser(String email, int age) {
    // ...
}
~~~

Khi class được biên dịch có metadata tên tham số, chương trình reflection có thể đọc được hai tên `email` và `age`. Nếu class không chứa metadata này, reflection thường chỉ trả về các tên tổng hợp như `arg0` và `arg1`.

Trong JDK, tùy chọn compiler dùng để ghi tên tham số vào class file là `-parameters`:

~~~bash
javac -parameters UserService.java
~~~

Đây là tùy chọn của **compiler `javac`**, không phải tùy chọn JVM khi chạy. Đặt nó trong lệnh biên dịch hoặc cấu hình build tool để class file đầu ra có thông tin tên tham số.

Parameter metadata hữu ích khi framework hoặc thư viện cần ánh xạ tên tham số với dữ liệu bên ngoài, ví dụ:

- Framework web ánh xạ tham số request vào tham số phương thức.
- Framework dependency injection dùng tên tham số để hỗ trợ phân giải dependency.
- Thư viện ánh xạ dữ liệu dùng tên tham số constructor để tạo đối tượng.
- Công cụ CLI hoặc RPC dùng tên tham số để tạo trợ giúp, binding hoặc thông báo lỗi dễ hiểu hơn.
- Công cụ logging và tracing hiển thị tên tham số khi phân tích lời gọi.

Khả năng tận dụng metadata phụ thuộc vào framework, phiên bản và cấu hình của framework đó. Một số framework còn yêu cầu annotation hoặc cấu hình tường minh.

## 2. `-parameters` hoạt động như thế nào?

Khi biên dịch Java, `javac` chuyển mã nguồn thành bytecode và ghi cấu trúc lớp vào file `.class`. Nếu bật `-parameters`, compiler ghi thêm thuộc tính `MethodParameters` trong class file cho các phương thức và constructor tương ứng.

Thuộc tính này lưu tên và một số cờ của từng tham số. JVM Reflection API có thể đọc thông tin đó khi class được nạp.

Quy trình:

~~~text
Source code
    |
    | javac -parameters
    v
Class file (.class)
    |
    | chứa MethodParameters
    v
Class loader nạp class
    |
    | Reflection API
    v
Parameter.getName() -> tên tham số nguồn
~~~

Nếu không bật `-parameters`, compiler vẫn tạo bytecode chạy bình thường. Chương trình vẫn gọi được phương thức, truyền đối số theo đúng thứ tự và dùng reflection để lấy kiểu tham số. Điểm khác biệt là tên tham số nguồn thường không có trong metadata dành cho Reflection API.

`-parameters` không thay đổi:

- Chữ ký phương thức ở cấp JVM (method descriptor).
- Thứ tự hoặc kiểu tham số.
- Quy tắc overload hay cách gọi phương thức.
- Giá trị được truyền vào phương thức.
- Hành vi thực thi của chương trình.

Nó bổ sung metadata vào class file, có thể làm file tăng nhẹ kích thước và khiến tên tham số trở thành thông tin có thể quan sát khi chạy.

## 3. Đọc tên tham số bằng Java Reflection

Java Reflection cung cấp lớp `java.lang.reflect.Parameter` để biểu diễn một tham số của phương thức hoặc constructor. Có thể lấy danh sách tham số từ `Executable`, lớp cha chung của `Method` và `Constructor`.

Các API thường dùng:

| API | Ý nghĩa |
|---|---|
| `Executable.getParameters()` | Lấy các tham số theo thứ tự khai báo. |
| `Parameter.getName()` | Trả về tên tham số; nếu không có tên được lưu, thường trả về tên tổng hợp như `arg0`. |
| `Parameter.isNamePresent()` | Cho biết tên tham số có được lưu trong class file để reflection sử dụng hay không. |
| `Parameter.getType()` | Lấy kiểu khai báo của tham số. |
| `Parameter.getModifiers()` | Lấy các modifier áp dụng cho tham số, nếu có. |
| `Parameter.isImplicit()` | Kiểm tra tham số có được compiler ngầm thêm vào hay không. |
| `Parameter.isSynthetic()` | Kiểm tra tham số có được compiler đánh dấu synthetic hay không. |

Luôn kiểm tra `isNamePresent()` trước khi xem `getName()` là tên có ý nghĩa trong mã nguồn. Giá trị `arg0` không chứng minh rằng người viết mã đã đặt tên tham số là `arg0`.

## 4. Ví dụ chạy được: so sánh có và không có `-parameters`

Tạo file `src/ParameterMetadataDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterMetadataDemo {

    public void greet(String recipient, int repeat) {
        // Phương thức dùng để minh họa metadata.
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterMetadataDemo.class.getDeclaredMethod(
                "greet", String.class, int.class);

        System.out.println("method=" + method.getName());

        for (Parameter parameter : method.getParameters()) {
            System.out.printf(
                    "name=%s, present=%s, type=%s%n",
                    parameter.getName(),
                    parameter.isNamePresent(),
                    parameter.getType().getSimpleName());
        }
    }
}
~~~

Tạo hai thư mục output riêng để so sánh:

~~~bash
mkdir -p out-with out-without
~~~

### Biên dịch có metadata

~~~bash
javac --release 17 -parameters -d out-with src/ParameterMetadataDemo.java
java -cp out-with ParameterMetadataDemo
~~~

Stdout:

~~~text
method=greet
name=recipient, present=true, type=String
name=repeat, present=true, type=int
~~~

### Biên dịch không có metadata

~~~bash
javac --release 17 -d out-without src/ParameterMetadataDemo.java
java -cp out-without ParameterMetadataDemo
~~~

Stdout:

~~~text
method=greet
name=arg0, present=false, type=String
name=arg1, present=false, type=int
~~~

Hai bản build đều chạy cùng logic và cùng chữ ký phương thức. Bản đầu có thể đọc tên nguồn vì được biên dịch với `-parameters`; bản thứ hai không có tên tham số trong metadata reflection nên `isNamePresent()` trả về `false`.

Trên Windows PowerShell, có thể tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force out-with, out-without | Out-Null
javac --release 17 -parameters -d out-with src/ParameterMetadataDemo.java
java -cp out-with ParameterMetadataDemo
javac --release 17 -d out-without src/ParameterMetadataDemo.java
java -cp out-without ParameterMetadataDemo
~~~

Nếu chạy lại lệnh biên dịch vào cùng thư mục output sau khi đổi tùy chọn, nên xóa hoặc tạo mới thư mục output trước. Nếu không, class file cũ có thể còn sót lại và làm kết quả kiểm tra khó hiểu.

## 5. Kiểm tra bytecode bằng `javap`

`javap` là công cụ disassembler đi kèm JDK. Tùy chọn `-v` hoặc `-verbose` hiển thị thuộc tính chi tiết trong class file; `-p` hiển thị cả thành viên private.

Kiểm tra bản build có metadata:

~~~bash
javap -v -p -classpath out-with ParameterMetadataDemo
~~~

Trong phần khai báo phương thức `greet`, kết quả có mục `MethodParameters` với tên tham số `recipient` và `repeat`. Bản build không bật `-parameters` thường không có mục `MethodParameters` chứa các tên nguồn đó.

Có thể lọc output trên Linux/macOS:

~~~bash
javap -v -p -classpath out-with ParameterMetadataDemo | grep -A4 MethodParameters
~~~

Trên PowerShell:

~~~powershell
javap -v -p -classpath out-with ParameterMetadataDemo | Select-String -Pattern "MethodParameters" -Context 0,4
~~~

Đây là cách hữu ích để kiểm tra artifact thực tế trong CI hoặc JAR phát hành, nhất là khi mã nguồn có `-parameters` nhưng build pipeline có thể không áp dụng tùy chọn cho tất cả module.

## 6. Phân biệt `-parameters` với debug information `-g`

Một nhầm lẫn phổ biến là cho rằng chỉ cần bật debug information bằng `-g` thì Reflection API sẽ biết tên tham số. Hai loại thông tin này có mục đích khác nhau.

| Tùy chọn | Dữ liệu được ghi | Mục đích |
|---|---|---|
| `-parameters` | Tên tham số trong thuộc tính `MethodParameters`. | Cho phép Reflection API đọc tên tham số qua `Parameter.getName()` và kiểm tra bằng `isNamePresent()`. |
| `-g` | Thông tin debug như số dòng, biến cục bộ và nguồn. | Hỗ trợ debugger và công cụ phân tích bytecode. |
| `-g:vars` | Thông tin biến cục bộ trong `LocalVariableTable`. | Hỗ trợ debugger xem tên biến cục bộ và phạm vi của chúng. |
| `-g:none` | Không ghi các nhóm debug information được điều khiển bởi tùy chọn này. | Giảm dữ liệu debug trong artifact. |

`LocalVariableTable` và `MethodParameters` là các thuộc tính class file khác nhau. Việc có tên biến trong debug table không đồng nghĩa với việc `Parameter.isNamePresent()` sẽ trả về `true`.

Nếu ứng dụng hoặc framework cần tên tham số qua Java Reflection, hãy bật `-parameters` một cách rõ ràng. Có thể kết hợp cả hai:

~~~bash
javac --release 17 -parameters -g -d out src/ParameterMetadataDemo.java
~~~

## 7. Áp dụng với constructor và method overload

`-parameters` hữu ích cho cả tham số phương thức và constructor. Để đọc tên tham số constructor, dùng `Constructor.getParameters()` tương tự như với `Method`.

Ví dụ:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class User {
    private final String email;
    private final int age;

    public User(String email, int age) {
        this.email = email;
        this.age = age;
    }

    public static void main(String[] args) throws Exception {
        Constructor<User> constructor =
                User.class.getConstructor(String.class, int.class);

        for (Parameter parameter : constructor.getParameters()) {
            System.out.println(
                    parameter.getName() + ": " + parameter.isNamePresent());
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -parameters -d out User.java
java -cp out User
~~~

Stdout:

~~~text
email: true
age: true
~~~

Với method overload, hãy chọn đúng method bằng tên và danh sách kiểu tham số. Không nên chỉ tìm theo tên vì có thể có nhiều method cùng tên.

~~~java
Method method = UserService.class.getDeclaredMethod(
        "find", String.class, int.class);
Parameter[] parameters = method.getParameters();
~~~

Tên tham số được lưu theo thứ tự khai báo. `-parameters` không làm thay đổi cách Java phân biệt overload; việc lựa chọn method bằng reflection vẫn dựa trên tên và kiểu tham số.

## 8. Tên tham số có phải một phần chữ ký phương thức không?

Tên tham số không phải thành phần của method descriptor mà JVM dùng để phân biệt các phương thức. Ví dụ hai khai báo sau có cùng tên phương thức và kiểu tham số:

~~~java
public void update(String email) { }
public void update(String address) { }
~~~

Đây không phải hai overload hợp lệ vì tên tham số không làm chữ ký phương thức khác nhau. Kiểu và thứ tự tham số mới quyết định overload.

Do đó, bật `-parameters` không thay đổi quy tắc liên kết bytecode của phương thức. Tuy nhiên, tên được ghi lại có thể ảnh hưởng đến framework hoặc thư viện dùng reflection để ánh xạ dữ liệu theo tên. Vì vậy, nếu framework phụ thuộc vào tên tham số, thay đổi tên trong mã nguồn có thể làm thay đổi hành vi binding dù method descriptor vẫn giống nhau.

Đối với API công khai, hãy cân nhắc tên tham số như một phần của trải nghiệm người dùng framework. Nếu tên phải ổn định qua các lần đổi tên nội bộ, có thể dùng annotation hoặc cấu hình tường minh do framework hỗ trợ thay vì phụ thuộc hoàn toàn vào tên nguồn.

## 9. Tích hợp `-parameters` với Maven

Với Maven Compiler Plugin, có thể bật parameter metadata bằng cấu hình `<parameters>true</parameters>`. Ví dụ phần plugin trong `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>17</release>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`<parameters>true</parameters>` yêu cầu compiler ghi tên tham số vào class file. `<release>17</release>` đặt API và bytecode mục tiêu Java 17.

Trong dự án thực tế, nên khai báo phiên bản Maven Compiler Plugin được dự án phê duyệt và quản lý tập trung trong `pluginManagement` nếu có nhiều module. Với Maven multi-module, kiểm tra cấu hình áp dụng cho từng module tạo ra class file mà framework cần đọc.

Sau khi build, có thể kiểm tra artifact:

~~~bash
mvn clean compile
javap -v -p -classpath target/classes com.example.ParameterMetadataDemo
~~~

Thay tên lớp trong lệnh `javap` theo package và class thực tế của dự án.

## 10. Tích hợp `-parameters` với Gradle

Trong Gradle Groovy DSL (`build.gradle`), thêm tùy chọn compiler cho mọi task JavaCompile:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Trong Gradle Kotlin DSL (`build.gradle.kts`):

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Nếu dự án có nhiều source set hoặc module, cấu hình ở cấp build phù hợp để các task biên dịch liên quan đều nhận tùy chọn. Có thể kiểm tra lệnh compiler trong log build hoặc dùng `javap -v` trên class file đầu ra.

Không nên thêm tùy chọn vào task test runtime với kỳ vọng nó thay đổi class đã biên dịch. Metadata phải được tạo trong giai đoạn compile của class cần introspection.

## 11. Khi nào nên bật và khi nào cần kiểm tra?

Nên bật `-parameters` khi:

- Framework cần suy ra tên tham số phương thức hoặc constructor.
- Thư viện reflection dùng tên tham số để ánh xạ dữ liệu.
- Ứng dụng muốn tạo thông báo lỗi, tài liệu hoặc công cụ trợ giúp từ chữ ký API.
- Một thành phần phụ thuộc đã yêu cầu rõ ràng parameter metadata.

Có thể không cần bật nếu ứng dụng không sử dụng tên tham số lúc runtime. Với thư viện phân phối cho bên thứ ba, hãy kiểm tra yêu cầu của framework mục tiêu và quyết định chính sách build thống nhất.

Khi debug một lỗi binding theo tên, kiểm tra lần lượt:

1. Class file thực tế có được biên dịch với `-parameters` không?
2. Đúng class file hoặc JAR có đang được nạp lúc chạy không?
3. `Parameter.isNamePresent()` trả về `true` không?
4. Framework có dùng đúng method/constructor và đúng phiên bản thư viện không?
5. Framework có cần annotation hoặc cấu hình bổ sung không?
6. Có bước obfuscation, shading, bytecode enhancement hoặc đóng gói nào làm mất hay thay đổi metadata không?

Một dependency bên ngoài không tự có tên tham số chỉ vì ứng dụng của bạn được build với `-parameters`. Tùy chọn cần được áp dụng khi biên dịch chính class chứa phương thức hoặc constructor mà framework muốn introspect.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `getName()` trả về `arg0`, `arg1` | Class file không có tên tham số dành cho reflection. | Biên dịch lại class đó với `javac -parameters`. |
| `isNamePresent()` trả về `false` | `MethodParameters` không có trong class file được nạp. | Kiểm tra tùy chọn compiler và dùng `javap -v` trên đúng artifact. |
| Đã bật `-g` nhưng reflection vẫn trả `arg0` | Debug local-variable metadata không thay thế `MethodParameters`. | Bật `-parameters` riêng. |
| Local build có tên nhưng CI không có | Build task hoặc module trên CI không nhận tùy chọn. | Kiểm tra lệnh `javac` thực tế và cấu hình Maven/Gradle cho mọi compile task liên quan. |
| Source có tên mới nhưng runtime hiển thị tên cũ | JVM đang nạp class file/JAR cũ hoặc dependency trùng. | Clean build, kiểm tra classpath/module path và vị trí class được nạp. |
| Một số tham số có trạng thái đặc biệt | Compiler hoặc ngôn ngữ có thể tạo tham số implicit/synthetic. | Kiểm tra `isImplicit()`, `isSynthetic()` và chữ ký constructor/method tương ứng. |
| Framework vẫn không bind được dù `isNamePresent()` là `true` | Framework có quy tắc binding hoặc annotation riêng. | Kiểm tra tài liệu framework và cấu hình/annotation của endpoint hoặc constructor. |

## 13. Checklist phát hành

- Đã xác định framework hoặc thư viện có cần tên tham số lúc runtime hay không.
- `javac` nhận `-parameters` khi biên dịch class cần introspection.
- Cấu hình Maven/Gradle áp dụng cho đúng module và source set.
- Đã kiểm tra `Parameter.isNamePresent()` trên artifact được build.
- Đã dùng `javap -v` để xác nhận `MethodParameters` trong class file.
- Không nhầm `-parameters` với `-g` hoặc `LocalVariableTable`.
- Kiểm tra JAR cuối cùng sau các bước shading, obfuscation hoặc bytecode transformation.
- Nếu tên tham số là một phần của binding contract, có kiểm thử để phát hiện thay đổi tên ngoài ý muốn.

`-parameters` là một tùy chọn biên dịch nhỏ nhưng có ý nghĩa lớn với các hệ thống dùng reflection. Hãy bật nó ở bước tạo class file, xác nhận bằng `Parameter.isNamePresent()` và `javap -v`, rồi kiểm tra hành vi binding ở framework thực tế.
