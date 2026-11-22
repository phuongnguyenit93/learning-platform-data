# Phân biệt mức cú pháp, định dạng class và API nền tảng

Khi biên dịch một ứng dụng Java để chạy trên một phiên bản Java cụ thể, cần kiểm tra ba lớp tương thích độc lập: **cú pháp ngôn ngữ**, **định dạng tệp class** và **API nền tảng**. Một chương trình có thể dùng cú pháp cũ và tạo class file đúng phiên bản Java 9 nhưng vẫn gọi nhầm API chỉ xuất hiện ở Java mới hơn. Khi đó, compiler có thể biên dịch thành công nhưng ứng dụng lại lỗi lúc chạy trên Java 9.

Từ JDK 9, lựa chọn **javac --release** giúp ràng buộc cả ba lớp tương thích trong cùng một lần biên dịch. Đây là cách nên dùng khi cần tạo ứng dụng hướng đến một phiên bản Java cụ thể.

## 1. Ba lớp tương thích khác nhau

| Lớp tương thích | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Mức cú pháp (source language level)** | Compiler có chấp nhận cấu trúc ngôn ngữ này không? | **var** chỉ được dùng làm biến cục bộ từ Java 10 |
| **Định dạng class (class-file format)** | JVM đích có đọc được bytecode đã tạo không? | Java 9 dùng major version 53; Java 10 dùng 54 |
| **API nền tảng (platform API)** | Các lớp, phương thức và trường mà chương trình gọi có tồn tại trong Java SE đích không? | **List.of** có từ Java 9; **String.isBlank** có từ Java 11 |

Ba lớp này liên quan với nhau nhưng không thể thay thế nhau. Chọn cú pháp Java 9 không tự động bảo đảm chương trình chỉ gọi API Java 9. Tạo class file phiên bản 53 cũng không tự động loại bỏ tham chiếu đến phương thức được bổ sung ở Java 11.

### Mức cú pháp

Mức cú pháp quyết định những tính năng ngôn ngữ mà compiler cho phép trong mã nguồn. Ví dụ:

- Java 9 hỗ trợ private method trong interface, diamond operator với anonymous class và try-with-resources với biến đã khai báo trước.
- Biến cục bộ dùng từ khóa **var** được giới thiệu ở Java 10.
- Record được chuẩn hóa ở Java 16.

Nếu dự án cần chạy trên Java 9, mã nguồn không được phụ thuộc vào cú pháp chỉ xuất hiện từ Java 10 trở đi. Tùy chọn **--source 9** yêu cầu javac áp dụng quy tắc cú pháp và ngôn ngữ của Java 9.

### Định dạng class

Sau khi biên dịch, mỗi lớp Java được lưu thành tệp **.class**. Phần header của tệp ghi nhận phiên bản định dạng class bằng major version. JVM kiểm tra phiên bản này khi nạp lớp.

Một số giá trị thường gặp:

| Phiên bản Java | Class-file major version |
|---:|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

Nếu một lớp có major version cao hơn mức JVM hỗ trợ, JVM từ chối nạp lớp và thường báo **UnsupportedClassVersionError**. Ví dụ, class file được tạo cho Java 10 có major version 54 nên không thể chạy trực tiếp trên JVM Java 9 chỉ hỗ trợ đến major version 53.

Tùy chọn **--target 9** yêu cầu javac tạo class file phù hợp với Java 9. Nó điều khiển định dạng bytecode, không phải danh sách API mà mã nguồn được phép gọi.

### API nền tảng

API nền tảng là các package, class, interface, constructor, method và field do Java cung cấp. API có thể được bổ sung qua từng phiên bản dù cú pháp ngôn ngữ và định dạng class vẫn giữ nguyên.

Ví dụ:

- **List.of(...)** được bổ sung trong Java 9.
- **String.isBlank()** được bổ sung trong Java 11.

Nếu ứng dụng gọi **String.isBlank()** nhưng chạy trên Java 9, class file vẫn có thể mang major version 53; tuy nhiên, lớp String của Java 9 không có phương thức đó. Khi lời gọi được thực hiện, ứng dụng có thể gặp **NoSuchMethodError**.

Đây là lý do chỉ kiểm soát cú pháp và class-file version là chưa đủ. Cần kiểm soát cả tập API mà compiler dùng để kiểm tra mã nguồn.

## 2. Các tùy chọn của javac kiểm soát điều gì?

| Tùy chọn | Kiểm soát | Không tự bảo đảm |
|---|---|---|
| **--source 9** | Quy tắc cú pháp và ngôn ngữ Java 9 | API chỉ có trong Java 9 |
| **--target 9** | Class-file format phù hợp Java 9 | Cú pháp Java 9 và API Java 9 |
| **--release 9** | Cú pháp Java 9, class file Java 9 và API nền tảng của Java 9 | Tương thích với mọi thư viện bên thứ ba, native library hoặc hành vi runtime |

### Vì sao ghép --source và --target vẫn có thể sai?

Giả sử đang dùng JDK 24 để biên dịch:

~~~bash
javac --source 9 --target 9 -d out src/NewerApi.java
~~~

Trong cấu hình này, compiler kiểm tra cú pháp theo Java 9 và tạo class file major version 53. Tuy nhiên, nếu không có cấu hình API tương ứng, javac vẫn có thể tra cứu API từ JDK đang dùng để biên dịch.

Do đó, mã gọi **String.isBlank()** có thể biên dịch thành công trên JDK 24 dù phương thức này chưa tồn tại trong Java 9. Class file trông có vẻ đúng phiên bản nhưng vẫn không tương thích API khi chạy trên Java 9.

Javac hiện cảnh báo rằng ghép **--source** và **--target** không tự đặt system modules của phiên bản đích, đồng thời khuyến nghị dùng **--release**.

## 3. Dùng --release để biên dịch hướng đến Java 9

Tùy chọn **--release N** yêu cầu javac biên dịch theo Java SE release N. Với Java 9, compiler đồng thời:

1. Chấp nhận cú pháp và tính năng ngôn ngữ thuộc Java 9.
2. Sinh class file có định dạng của Java 9, major version 53.
3. Kiểm tra mã nguồn dựa trên các API nền tảng được cung cấp trong Java 9.

Ví dụ:

~~~bash
javac --release 9 -d out src/Main.java
~~~

Lệnh này có ý nghĩa rõ ràng hơn việc tự ghép **--source 9 --target 9**. Khi cần tạo artifact chạy trên Java 9, hãy đặt release trong cấu hình biên dịch của dự án để mọi lần build đều áp dụng cùng một hợp đồng tương thích.

**--release** có từ JDK 9. Một JDK mới hơn có thể biên dịch cho một số release cũ mà nó còn hỗ trợ; danh sách chính xác được hiển thị trong **javac --help**. Không thể yêu cầu compiler tạo một release tùy ý nằm ngoài danh sách hỗ trợ của chính compiler đó.

## 4. Ví dụ: API Java 9 được chấp nhận

**List.of(...)** là API được bổ sung ở Java 9. Chương trình sau có thể biên dịch với release 9:

Tệp **Main.java**:

~~~java
import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");
        System.out.println(names);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 9 -d out src/Main.java
java -cp out Main
~~~

Kết quả:

~~~text
[An, Binh]
~~~

Có thể dùng **javap -verbose** để kiểm tra class file đã tạo:

~~~bash
javap -verbose -classpath out Main
~~~

Trong phần đầu ra, tìm dòng:

~~~text
major version: 53
~~~

Điều này xác nhận định dạng class tương ứng Java 9. Lệnh **javap** kiểm tra class file; nó không thay thế việc kiểm tra API hoặc chạy thử trên runtime đích.

## 5. Ví dụ: API Java mới hơn bị từ chối

**String.isBlank()** được bổ sung ở Java 11. Nếu mã nguồn gọi phương thức này:

~~~java
public class NewerApi {
    public static void main(String[] args) {
        System.out.println("".isBlank());
    }
}
~~~

Biên dịch theo Java 9:

~~~bash
javac --release 9 -d out src/NewerApi.java
~~~

Compiler báo không tìm thấy phương thức **isBlank()** trên lớp **String** trong tập API Java 9. Đây là kết quả đúng: chương trình không được tham chiếu API chưa tồn tại trong phiên bản đích.

Nếu đổi sang:

~~~bash
javac --release 11 -d out src/NewerApi.java
~~~

Mã nguồn sẽ được kiểm tra theo API Java 11 và tạo class file major version 55.

Tương tự, nếu dùng cú pháp **var**:

~~~java
public class VarSyntax {
    public static void main(String[] args) {
        var message = "Java";
        System.out.println(message);
    }
}
~~~

Lệnh **javac --release 9** từ chối mã nguồn vì **var** chưa thuộc ngôn ngữ Java 9. Đổi sang release 10 trở lên thì cú pháp này được chấp nhận.

Hai ví dụ trên cho thấy **--release** kiểm tra cả cú pháp và API; class-file version là đầu ra thứ ba được ràng buộc theo release đã chọn.

## 6. Cấu hình trong hệ thống build

Để tránh mỗi lập trình viên phải nhớ truyền tùy chọn khi chạy javac, nên khai báo release trong build script.

### Gradle

Với Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 9
}
~~~

Với Kotlin DSL:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release = 9
}
~~~

Có thể cấu hình Java toolchain riêng để chọn JDK thực thi compiler. Toolchain xác định bộ JDK dùng khi build; **options.release** xác định nền tảng Java mà mã nguồn hướng đến. Hai cấu hình này giải quyết hai việc khác nhau.

### Maven

Trong **pom.xml**, cấu hình thuộc tính release của Maven Compiler Plugin:

~~~xml
<properties>
    <maven.compiler.release>9</maven.compiler.release>
</properties>
~~~

Cần dùng phiên bản Maven Compiler Plugin có hỗ trợ tùy chọn release. Khi đó plugin truyền cấu hình tương ứng cho javac trong quá trình compile.

Không nên chỉ đặt source/target rồi cho rằng API đã được giới hạn theo phiên bản đích. Hãy xác minh build log hoặc cấu hình compiler thực tế đang sử dụng.

## 7. Kiểm tra artifact và runtime đích

Một quy trình kiểm tra tương thích nên thực hiện các bước sau:

1. Xác định phiên bản Java thấp nhất mà ứng dụng phải hỗ trợ.
2. Cấu hình **--release** đúng phiên bản đó trong build.
3. Kiểm tra class file bằng **javap -verbose** để xác nhận major version.
4. Chạy ứng dụng trên phiên bản runtime thấp nhất đã cam kết hỗ trợ.
5. Kiểm tra thư viện bên thứ ba, plugin, annotation processor và native library theo cùng yêu cầu tương thích.

Có thể kiểm tra phiên bản runtime bằng:

~~~bash
java --version
javac --version
~~~

Nếu build trên JDK mới và chạy trên JDK cũ, cần phân biệt:

- JDK dùng để biên dịch là công cụ tạo artifact.
- Release là phiên bản ngôn ngữ, class file và API mà artifact hướng đến.
- JRE/JDK dùng để chạy phải hỗ trợ class file và API mà ứng dụng thực sự sử dụng.

**--release 9** kiểm tra API nền tảng Java 9. Nó không kiểm tra toàn bộ API của dependency bên thứ ba. Một thư viện bên ngoài có thể được biên dịch cho Java 17 hoặc gọi API Java 11, khiến ứng dụng tổng thể không chạy được trên Java 9 dù phần mã nguồn của dự án đã dùng **--release 9**.

Tùy chọn này cũng không chuyển đổi native library sang hệ điều hành khác, không thay thế kiểm thử tích hợp và không bảo đảm hành vi nghiệp vụ giống hệt giữa các runtime.

## 8. Cách đọc lỗi tương thích

| Lỗi hoặc dấu hiệu | Lớp tương thích cần kiểm tra | Hướng xử lý |
|---|---|---|
| Compiler báo cú pháp hoặc từ khóa không hợp lệ | Mức cú pháp | Kiểm tra tính năng ngôn ngữ và release đang đặt |
| **UnsupportedClassVersionError** | Định dạng class | Kiểm tra major version bằng javap và phiên bản JVM chạy |
| **NoSuchMethodError** | API nền tảng hoặc API dependency | Xác định phương thức có tồn tại ở runtime đích không; kiểm tra dependency |
| **NoClassDefFoundError** | API, dependency hoặc classpath/module path | Kiểm tra class bị thiếu và cách đóng gói/phân phối |
| Build thành công nhưng chỉ lỗi trên runtime cũ | Cả ba lớp và dependency | Kiểm tra release, class file, API và chạy thử trên runtime thấp nhất |

Không nên kết luận mọi lỗi runtime đều do sai class-file version. Một class có thể được JVM chấp nhận nhưng vẫn tham chiếu đến API không có trên runtime đó. Ngược lại, API có tồn tại nhưng class file quá mới thì JVM vẫn từ chối nạp lớp trước khi ứng dụng thực thi.

## 9. Quy tắc áp dụng

- Khi cần tương thích với Java 9, cấu hình **--release 9** ở cấp build.
- Phân biệt rõ source level, class-file target và API platform; mỗi yếu tố kiểm soát một loại tương thích.
- Dùng **javap -verbose** để xác minh major version, không suy đoán chỉ từ tên JDK đã cài.
- Kiểm tra dependency và native library riêng vì **--release** không kiểm soát toàn bộ mã bên ngoài.
- Chạy kiểm thử trên runtime thấp nhất mà sản phẩm cam kết hỗ trợ.

Một artifact chỉ thực sự hướng đến Java 9 khi cú pháp được giới hạn theo Java 9, class file phù hợp major version 53 và mọi API nền tảng được tham chiếu đều có trong Java 9. **--release 9** gom ba yêu cầu đó thành một cấu hình biên dịch rõ ràng, dễ kiểm tra và duy trì.