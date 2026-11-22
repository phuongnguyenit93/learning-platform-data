# Ngăn gọi API mới ngoài nền tảng đích

## 1. Vấn đề cần giải quyết

Khi một dự án được biên dịch bằng JDK mới nhưng phải chạy trên JDK cũ hơn, mã nguồn có thể vô tình gọi API chỉ xuất hiện ở JDK mới. Compiler vẫn có thể tạo class file mang phiên bản bytecode cũ nếu chỉ dùng -source và -target, nhưng chương trình vẫn có thể lỗi khi chạy trên nền tảng đích.

Ví dụ, JDK 24 có phương thức List.getFirst() được bổ sung trong Java 21 thông qua SequencedCollection. Nếu biên dịch mã gọi phương thức này bằng -source 17 -target 17 trên JDK 24, compiler vẫn nhìn thấy API của JDK 24 và có thể chấp nhận lời gọi. Class file tạo ra mang phiên bản Java 17, nhưng JDK 17 không có phương thức đó. Khi chạy, chương trình có thể ném NoSuchMethodError.

Cách phù hợp để giới hạn cả cú pháp, phiên bản bytecode và Java platform API là dùng tùy chọn javac --release.

## 2. --release làm gì?

--release được đưa vào javac từ JDK 9. Nó kết hợp ba yêu cầu khi biên dịch:

1. Giới hạn cú pháp ngôn ngữ Java theo release được chọn.
2. Tạo class file tương thích với phiên bản bytecode của release đó.
3. Giới hạn Java SE API và API JDK được tài liệu hóa theo phiên bản release đó.

Ví dụ:

~~~bash
javac --release 17 -d out src/com/acme/App.java
~~~

Lệnh này biên dịch mã theo nền tảng Java 17. Nếu mã gọi một API chỉ được bổ sung sau Java 17, compiler sẽ báo lỗi ngay ở bước build.

Khi build bằng JDK 24 nhưng đặt --release 17, compiler dùng thông tin API của Java 17 thay vì toàn bộ API có trong JDK 24. Vì vậy, --release ngăn lỗi gọi nhầm API mới ngay cả khi máy build đã cài JDK mới hơn máy chạy.

Không ghép --release với -source hoặc -target trong cùng lệnh. --release đã quản lý cả source level và target bytecode.

## 3. Vì sao chỉ dùng -source và -target là chưa đủ?

Hai tùy chọn này giải quyết hai vấn đề riêng:

| Tùy chọn | Ý nghĩa |
|---|---|
| -source 17 | Chỉ chấp nhận cú pháp ngôn ngữ Java 17 |
| -target 17 | Tạo class file có định dạng bytecode Java 17 |
| --release 17 | Giới hạn cú pháp, bytecode và Java platform API ở Java 17 |

Nếu dùng JDK 24:

~~~bash
javac -source 17 -target 17 -d out src/NewPlatformApi.java
~~~

Compiler vẫn dùng API của JDK 24 để kiểm tra tên lớp, phương thức và trường. Nó có thể chấp nhận API chưa tồn tại trong Java 17. Kết quả chỉ bảo đảm định dạng class file ở mức Java 17, không bảo đảm các API được gọi có mặt ở Java 17.

Với --release:

~~~bash
javac --release 17 -d out src/NewPlatformApi.java
~~~

Compiler vừa tạo bytecode Java 17 vừa kiểm tra mã nguồn dựa trên API Java 17. Đây là khác biệt quyết định khi build bằng JDK mới cho runtime cũ.

## 4. Ví dụ: ngăn gọi List.getFirst() khi target Java 17

List.getFirst() là API được bổ sung trong Java 21 thông qua SequencedCollection. Một chương trình sử dụng phương thức này:

~~~java
import java.util.List;

public final class NewPlatformApi {
    public static void main(String[] args) {
        System.out.println(List.of("alpha", "beta").getFirst());
    }
}
~~~

Biên dịch với target Java 17:

~~~bash
javac --release 17 -d out17 src/NewPlatformApi.java
~~~

Compiler báo lỗi vì List trong Java 17 chưa có getFirst():

~~~text
src/NewPlatformApi.java:5: error: cannot find symbol
        System.out.println(List.of("alpha", "beta").getFirst());
                                                   ^
  symbol:   method getFirst()
  location: interface List<String>
1 error
~~~

Lỗi được phát hiện ngay lúc build. Không cần chờ ứng dụng được triển khai lên máy Java 17.

Nếu ứng dụng thực sự yêu cầu Java 21, đổi target sang 21:

~~~bash
javac --release 21 -d out21 src/NewPlatformApi.java
java -cp out21 NewPlatformApi
~~~

Output:

~~~text
alpha
~~~

Kết quả kiểm thử trên OpenJDK 24.0.2:

| Cách biên dịch | Kết quả |
|---|---|
| javac --release 17 | Compile fail vì List.getFirst() không có trong Java 17 |
| javac --release 21 | Compile pass |
| javac -source 17 -target 17 | Compile pass trên JDK 24, dù dùng API Java 21 |

Đây là ví dụ điển hình cho thấy class file version cũ không đồng nghĩa với việc mọi API được gọi đều có sẵn trên runtime cũ.

## 5. Hiểu lỗi ở thời điểm chạy

Nếu biên dịch mã gọi API mới bằng -source và -target, class file có thể được tạo thành công nhưng runtime cũ không cung cấp phương thức đó.

Một số lỗi thường gặp:

- NoSuchMethodError: lớp có tồn tại nhưng không có phương thức mà bytecode yêu cầu.
- NoSuchFieldError: lớp có tồn tại nhưng không có trường được tham chiếu.
- NoClassDefFoundError: runtime không tìm thấy class cần thiết.
- UnsupportedClassVersionError: runtime quá cũ để đọc phiên bản class file.

Cần phân biệt hai nhóm:

- API không có trên runtime: thường dẫn tới lỗi liên kết như NoSuchMethodError hoặc NoSuchFieldError khi đường chạy đó được thực thi.
- Bytecode mới hơn runtime hỗ trợ: có thể dẫn tới UnsupportedClassVersionError khi JVM nạp class.

--release xử lý đồng thời hai giới hạn của Java platform: API có sẵn và định dạng bytecode. Nó giúp phát hiện nhiều lỗi trước khi phát hành.

## 6. Chọn release theo runtime thấp nhất được hỗ trợ

Trước khi cấu hình build, xác định phiên bản Java thấp nhất mà sản phẩm cam kết hỗ trợ.

Ví dụ:

| Chính sách runtime | Cấu hình compile |
|---|---|
| Chỉ hỗ trợ Java 17 trở lên | --release 17 |
| Chỉ hỗ trợ Java 21 trở lên | --release 21 |
| Hỗ trợ Java 17 và các JDK mới hơn | --release 17 |
| Chỉ hỗ trợ Java 24 | --release 24 |

Nếu hỗ trợ nhiều phiên bản JDK mới hơn, target nên là phiên bản thấp nhất mà sản phẩm cần chạy. Mã được biên dịch theo release thấp hơn có thể chạy trên JDK mới hơn theo chính sách tương thích của Java, miễn là dependency và môi trường runtime cũng tương thích.

Không chọn target theo JDK đang cài trên máy lập trình viên. Hãy chọn theo hợp đồng hỗ trợ runtime của sản phẩm.

Kiểm tra các release mà compiler đang dùng hỗ trợ:

~~~bash
javac --help
~~~

--release chỉ hỗ trợ các phiên bản nền tảng mà JDK compiler hiện tại cung cấp thông tin API tương ứng. Nếu cần target một release mới hơn compiler đang dùng, phải nâng JDK build.

## 7. Cấu hình Maven

Với Maven Compiler Plugin hiện đại, cấu hình maven.compiler.release trong pom.xml:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
    </plugins>
</build>
~~~

Sau đó build:

~~~bash
mvn clean verify
~~~

Maven Compiler Plugin chuyển thuộc tính release thành tùy chọn --release của javac. Hãy dùng phiên bản plugin có hỗ trợ thuộc tính này và kiểm tra log build để xác nhận compiler thực sự nhận release mong muốn.

Không cấu hình riêng maven.compiler.source và maven.compiler.target để thay thế --release khi build bằng JDK mới cho runtime cũ.

## 8. Cấu hình Gradle

Với Gradle Kotlin DSL, có thể khai báo toolchain và release:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
~~~

Trong ví dụ:

- Toolchain chọn JDK 24 để chạy compiler.
- options.release = 17 giới hạn API, cú pháp và bytecode ở Java 17.

Cấu hình này cho phép build bằng compiler mới nhưng vẫn kiểm tra tương thích với Java 17.

Nếu muốn dùng JDK 17 làm compiler toolchain, đổi languageVersion thành 17. Dù chọn cách nào, nên cấu hình release rõ ràng để mục tiêu tương thích được thể hiện trong build.

Với Groovy DSL, cấu hình tương đương:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

## 9. --release không kiểm soát mọi dependency

--release giới hạn Java platform API mà compiler dùng để biên dịch mã nguồn hiện tại. Nó không tự xác minh mọi thư viện bên thứ ba có tương thích với runtime đích hay không.

Ví dụ, dự án target Java 17 nhưng thêm thư viện chỉ hỗ trợ Java 21. Mã ứng dụng có thể compile thành công nếu các kiểu và phương thức public của thư viện vẫn tương thích ở thời điểm biên dịch, nhưng lúc chạy trên Java 17 thư viện có thể gặp lỗi do bytecode hoặc API mới.

Cần kiểm tra riêng:

- Phiên bản Java tối thiểu mà từng dependency hỗ trợ.
- Phiên bản bytecode của dependency.
- Dependency bắc cầu và dependency runtime.
- API JDK mới được dependency gọi.
- Thư viện dùng reflection, MethodHandle, Class.forName hoặc service loading.
- Native library và thành phần phụ thuộc hệ điều hành.

Nếu class file của dependency có phiên bản cao hơn JVM đích hỗ trợ, runtime có thể ném UnsupportedClassVersionError. Nếu dependency gọi API không có trên runtime đích, lỗi liên kết có thể xuất hiện khi đường chạy đó được thực thi.

Hãy đọc metadata/release notes của dependency, quản lý phiên bản bằng dependency management và chạy test trên đúng JDK thấp nhất được hỗ trợ.

## 10. Các trường hợp --release không thể phát hiện đầy đủ

Một số API được sử dụng theo cách không thể kiểm tra chỉ bằng phân tích kiểu tĩnh của compiler:

- Tên class hoặc method được ghép thành chuỗi rồi nạp qua reflection.
- Method được tìm bằng MethodHandles hoặc reflection.
- Provider được phát hiện qua ServiceLoader và module layer.
- Class hoặc resource được tải theo cấu hình ngoài.
- Code được sinh và biên dịch ở runtime.
- Native code gọi ngược vào Java hoặc sử dụng API hệ điều hành.

Ví dụ:

~~~java
Class<?> type = Class.forName("com.acme.runtime.NewFeature");
~~~

Compiler không thể biết chuỗi tên class này có tồn tại trên runtime đích hay không. Khi chạy trên Java cũ, ClassNotFoundException có thể xảy ra.

Với các trường hợp đó, cần test tích hợp trên runtime đích, kiểm tra cấu hình và bổ sung kiểm tra dependency/API bằng công cụ phù hợp.

## 11. Preview features và release

Preview language feature được bật bằng --enable-preview. Preview chỉ được hỗ trợ theo release của JDK compiler tương ứng; không thể dùng preview của một JDK mới để tạo cam kết tương thích với runtime cũ hơn.

Ví dụ, khi thử preview feature trên JDK 24:

~~~bash
javac --release 24 --enable-preview -d out src/PreviewExample.java
java --enable-preview -cp out PreviewExample
~~~

Không dùng preview feature trong artifact cần tương thích rộng nếu runtime đích không đúng release preview tương ứng. Preview API và ngôn ngữ có thể thay đổi hoặc bị loại bỏ trước khi trở thành tính năng chính thức.

## 12. Kiểm tra bytecode và dependency sau build

Có thể dùng javap để xem phiên bản class file:

~~~bash
javap -verbose out/com/acme/App.class
~~~

Tìm dòng major version. Một số giá trị thường gặp:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

Kiểm tra major version chỉ xác nhận định dạng bytecode. Nó không chứng minh API được tham chiếu đều tồn tại trên runtime đích. Vì vậy, dùng --release ở bước compile và dùng runtime test để kiểm tra hành vi thực tế.

Có thể dùng jdeps để phân tích dependency và tìm tham chiếu tới JDK internal API:

~~~bash
jdeps --jdk-internals path/to/application.jar
~~~

jdeps bổ sung thông tin về dependency; nó không thay thế --release và cũng không tự chứng minh thư viện bên thứ ba hỗ trợ runtime nào.

## 13. Quy trình CI khuyến nghị

Một pipeline kiểm tra tương thích có thể thực hiện:

1. Chọn JDK build được dự án hỗ trợ.
2. Compile tất cả source set bằng --release của runtime thấp nhất.
3. Build dependency và kiểm tra phiên bản Java tối thiểu của chúng.
4. Chạy unit test trên JDK thấp nhất được hỗ trợ.
5. Chạy integration test trên các JDK runtime mục tiêu.
6. Kiểm tra các đường chạy reflection, ServiceLoader, JNI và cấu hình động.
7. Kiểm tra class file version của artifact khi có dependency bên ngoài.
8. Phát hành artifact cùng thông tin runtime tối thiểu đã kiểm thử.

Ví dụ ma trận kiểm thử:

| Build | Runtime test | Mục đích |
|---|---|---|
| JDK 24 với --release 17 | JDK 17 | Xác nhận mức tương thích tối thiểu |
| JDK 24 với --release 17 | JDK 21 | Xác nhận chạy trên runtime mới hơn |
| JDK 24 với --release 17 | JDK 24 | Kiểm tra môi trường build/runtime hiện tại |

Không chỉ chạy test trên JDK mới nhất. Nếu sản phẩm cam kết Java 17, test trên Java 17 là bước bắt buộc để phát hiện dependency hoặc hành vi runtime chưa được --release kiểm tra.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Code gọi API mới vẫn compile | Chỉ dùng -source và -target | Chuyển sang --release |
| --release báo cannot find symbol | API chưa tồn tại ở release được chọn | Dùng API cũ hơn hoặc nâng runtime tối thiểu |
| --release không được nhận diện | Đang dùng compiler JDK 8 hoặc cũ hơn | Dùng JDK 9+ để build |
| Dependency gây UnsupportedClassVersionError | Bytecode dependency mới hơn runtime | Chọn dependency tương thích hoặc nâng runtime |
| NoSuchMethodError trên máy khách | Dependency hoặc code gọi API không có trên runtime | Compile bằng --release và test trên runtime tối thiểu |
| Code reflection lỗi dù compile pass | Tên class/method được nạp động, compiler không kiểm tra được | Bổ sung integration test và kiểm tra cấu hình |
| Build local pass nhưng CI fail | Toolchain hoặc release cấu hình khác nhau | Khóa toolchain và cấu hình release trong build |
| API preview không chạy trên runtime khác | Preview gắn với release cụ thể | Không phát hành preview feature như API tương thích ổn định |

## 15. Checklist trước khi phát hành

- [ ] Đã xác định runtime thấp nhất được hỗ trợ.
- [ ] Đã cấu hình javac --release theo runtime đó.
- [ ] Không dùng riêng -source và -target để thay thế kiểm tra API.
- [ ] Build tool truyền đúng tùy chọn release.
- [ ] Không gọi API được bổ sung sau release mục tiêu.
- [ ] Dependency bên thứ ba hỗ trợ runtime tối thiểu.
- [ ] Đã kiểm tra reflection, MethodHandle, ServiceLoader và code tải động.
- [ ] Đã kiểm tra class file version của artifact khi cần.
- [ ] Đã chạy test trên JDK thấp nhất được hỗ trợ.
- [ ] Không phụ thuộc preview feature nếu cần tương thích rộng.
- [ ] Toolchain và cấu hình CI được thống nhất.

## Tài liệu tham khảo

- [javac Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Java Compiler API and --release — JEP 247](https://openjdk.org/jeps/247)
- [Java SE 21 List API — getFirst](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html)
- [Maven Compiler Plugin — compile using --release](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
