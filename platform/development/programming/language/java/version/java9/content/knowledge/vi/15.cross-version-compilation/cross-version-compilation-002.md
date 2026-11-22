# Mục đích của javac --release

Tùy chọn **--release** của **javac** giúp biên dịch mã nguồn bằng một JDK mới nhưng giới hạn kết quả theo một phiên bản Java SE được chọn. Nó kết hợp ba yêu cầu trong cùng một lựa chọn: quy tắc ngôn ngữ Java, định dạng bytecode và tập API công khai được hỗ trợ của phiên bản đích.

Ví dụ, dùng JDK 24 để biên dịch ứng dụng cho Java 17:

~~~bash
javac --release 17 -d out src/Main.java
~~~

Compiler sẽ kiểm tra cú pháp theo Java 17, tạo class file phù hợp Java 17 và chỉ cho phép dùng các API Java SE có trong phiên bản 17. Đây là mục đích quan trọng nhất của **--release**: giúp phát hiện sớm việc vô tình dùng cú pháp hoặc API mới hơn phiên bản Java mà ứng dụng cam kết hỗ trợ.

## 1. Vấn đề khi chỉ dùng -source và -target

Trước khi có **--release**, nhiều dự án dùng hai tùy chọn:

- **-source**: chọn phiên bản cú pháp/ngôn ngữ Java mà compiler chấp nhận.
- **-target**: chọn phiên bản bytecode/class file được tạo ra.

Ví dụ:

~~~bash
javac -source 11 -target 11 -d out src/Main.java
~~~

Hai tùy chọn này không tự giới hạn tập API mà compiler nhìn thấy. Nếu compiler đang chạy trên JDK 24, mã có thể tham chiếu một method chỉ xuất hiện từ Java 15 nhưng vẫn tạo class file mang phiên bản Java 11. Class đó có thể biên dịch thành công nhưng gặp **NoSuchMethodError** khi chạy trên Java 11.

Đây là khoảng cách giữa bytecode compatibility và API compatibility. Class file có phiên bản cũ không có nghĩa mọi API mà nó gọi đều tồn tại trên runtime cũ.

JDK 24.0.2 đã kiểm chứng khác biệt này:

- **-source 11 -target 11** vẫn biên dịch được ví dụ dùng **String.stripIndent()**, kèm cảnh báo về system modules.
- **--release 11** từ chối cùng mã nguồn vì API đó chưa có trong Java 11.

Vì vậy, khi build bằng JDK mới cho một Java release cũ hơn, **--release** thường là lựa chọn phù hợp hơn.

## 2. --release kiểm soát những gì?

Khi chạy:

~~~bash
javac --release 17 ...
~~~

compiler áp dụng đồng thời ba lớp kiểm tra:

| Thành phần | Điều được giới hạn |
|---|---|
| Source language | Cú pháp và tính năng ngôn ngữ được phép trong Java 17 |
| Target class file | Bytecode được tạo có định dạng tương thích Java 17 |
| Platform API | Chỉ các API công khai, được hỗ trợ của Java SE 17 được phép tham chiếu |

Ba giới hạn này bổ sung cho nhau. Nếu chỉ giới hạn source language, compiler vẫn có thể nhìn thấy API mới. Nếu chỉ giới hạn target bytecode, class file có thể chứa tham chiếu tới method runtime cũ không có.

**--release** được giới thiệu từ JDK 9 để cung cấp cách biên dịch đa phiên bản đáng tin cậy hơn. Nó hữu ích cho ứng dụng cần chạy trên một Java release thấp hơn JDK đang dùng để build, cũng như thư viện muốn công bố rõ phiên bản Java tối thiểu được hỗ trợ.

## 3. Khác nhau giữa --release, --source và --target

| Tùy chọn | Cú pháp/ngôn ngữ | Phiên bản bytecode | Tập API nền tảng |
|---|---:|---:|---:|
| **--source 17** | Java 17 | Theo target mặc định nếu không chỉ định riêng | API của JDK đang chạy compiler |
| **--target 17** | Theo source mặc định nếu không chỉ định riêng | Java 17 | API của JDK đang chạy compiler |
| **-source 17 -target 17** | Java 17 | Java 17 | API của JDK đang chạy compiler |
| **--release 17** | Java 17 | Java 17 | API công khai, được hỗ trợ của Java SE 17 |

Các điểm cần nhớ:

- **--source** và **--target** vẫn là các tùy chọn hợp lệ khi cần kiểm soát riêng từng chiều.
- Dùng riêng **-source/-target** không bảo đảm API tương thích với runtime đích.
- **--release N** gói cả ba mục tiêu vào một lựa chọn và tránh phải tự cấu hình API boot/platform tương ứng.
- Không kết hợp **--release** với **--source** hoặc **--target** trong cùng lệnh.
- Không dùng **--release** như một cách chọn JDK cài đặt. Compiler vẫn là compiler của JDK đang chạy.

Trên JDK 24, danh sách release mà compiler hỗ trợ được hiển thị bằng:

~~~bash
javac --help
~~~

Danh sách thay đổi theo phiên bản JDK. JDK 24.0.2 hỗ trợ **--release 8** đến **--release 24**. Không giả định mọi compiler đều hỗ trợ mọi release lịch sử; hãy xem danh sách của chính compiler trong build environment.

## 4. Ví dụ: biên dịch cho Java 17 bằng JDK 24

Giả sử dự án cần chạy từ Java 17 trở lên, nhưng máy build đã cài JDK 24.

Cấu trúc:

~~~text
project/
  src/
    ApiLevel.java
  out/
~~~

**Tệp src/ApiLevel.java:**

~~~java
public final class ApiLevel {
    public static void main(String[] args) {
        String text = "  Java 17  ";
        System.out.println(text.stripIndent().strip());
    }
}
~~~

Method **String.stripIndent()** có từ Java 15. Do đó, API này tồn tại trong Java 17 nhưng không tồn tại trong Java 11.

Biên dịch bằng JDK 24, giới hạn ở Java 17:

~~~bash
javac --release 17 -d out src/ApiLevel.java
~~~

Chạy bằng runtime JDK 24:

~~~bash
java -cp out ApiLevel
~~~

Output:

~~~text
Java 17
~~~

Lệnh biên dịch thành công vì cú pháp và API đều nằm trong phạm vi Java 17. Việc chạy trên JDK 24 cho thấy class file Java 17 vẫn chạy được trên runtime mới hơn tương thích.

Kiểm tra phiên bản class file:

~~~bash
javap -verbose -classpath out ApiLevel
~~~

Phần đầu output có:

~~~text
public final class ApiLevel
  minor version: 0
  major version: 61
~~~

Major version **61** tương ứng class file Java 17.

## 5. Ví dụ: --release phát hiện API mới hơn phiên bản đích

Giữ nguyên tệp **ApiLevel.java**, thử biên dịch cho Java 11:

~~~bash
javac --release 11 -d out11 src/ApiLevel.java
~~~

Compiler báo lỗi tương tự:

~~~text
error: cannot find symbol
        System.out.println(text.stripIndent().strip());
                               ^
  symbol:   method stripIndent()
  location: variable text of type String
~~~

Đây là kết quả mong muốn. Compiler đang kiểm tra chương trình như thể chỉ có API Java 11, nên không cho phép dùng method được thêm từ Java 15.

Nếu thay lệnh bằng:

~~~bash
javac -source 11 -target 11 -d out11 src/ApiLevel.java
~~~

JDK 24 có thể biên dịch thành công vì compiler vẫn nhìn thấy API của JDK 24. Điều đó không chứng minh class chạy được trên Java 11; runtime Java 11 không có **String.stripIndent()** và có thể ném **NoSuchMethodError** khi thực thi dòng lệnh đó.

Không nên dựa vào việc hạ class-file version để suy ra API compatibility. Hãy dùng **--release** để compiler kiểm tra cả hai.

## 6. API nào được phép dùng khi chọn một release?

Khi chọn **--release N**, compiler kiểm tra các API công khai và được hỗ trợ của Java SE release N. Các chi tiết triển khai nội bộ của JDK không trở thành API hợp lệ chỉ vì chúng có mặt trong JDK đang cài.

Ví dụ:

- **--release 8** giới hạn theo API Java SE 8.
- **--release 11** cho phép API được bổ sung trong Java 9, 10 và 11 nếu chúng thuộc Java SE và có trong release 11.
- **--release 17** cho phép API Java SE có trong release 17, bao gồm các API được thêm từ các release trước.
- **--release 24** cho phép API thuộc Java SE 24 mà compiler hỗ trợ.

Một số package mở rộng hoặc API đặc thù của nhà cung cấp không thuộc API Java SE được cam kết. Nếu ứng dụng phụ thuộc vào API riêng của một JDK distribution, cần kiểm tra riêng khả năng tương thích với nhà cung cấp và runtime triển khai.

**--release** cũng không phải công cụ phân tích mọi dependency của sản phẩm. Nó kiểm tra các tham chiếu mà compiler nhìn thấy trong lần biên dịch đó. Dependency JAR, mã được nạp động, reflection, JNI và module/plugin bên ngoài cần được kiểm tra bằng các bước phù hợp khác.

## 7. Dùng --release trong dự án nhiều module

Với ứng dụng modular, có thể dùng **--release** cùng module source path:

~~~bash
javac --release 17 \
    --module-source-path src \
    -d mods \
    -m com.example.app
~~~

Module descriptor và mã nguồn vẫn phải tuân theo khả năng của Java release đích. Nếu module sử dụng API chỉ có từ Java 21, biên dịch với **--release 17** sẽ báo lỗi tại tham chiếu đó.

Một dự án có nhiều module nhưng cùng yêu cầu Java tối thiểu nên thống nhất release target. Nếu mỗi module có target khác nhau, cần xác định rõ ranh giới bytecode/API giữa chúng và bảo đảm module được dùng ở runtime không đòi hỏi phiên bản mới hơn runtime chung.

**--release** không thay thế việc khai báo dependency trong **module-info.java**. Các directive **requires**, **exports**, **opens** và module path vẫn có nhiệm vụ riêng trong JPMS.

## 8. Preview features và giới hạn của release target

Preview feature gắn với một phiên bản Java cụ thể. Compiler hiện đại cho phép kết hợp **--enable-preview** với **--release** của chính feature release hiện tại, ví dụ trên JDK 24:

~~~bash
javac --release 24 --enable-preview -d out src/Main.java
~~~

Khi mã nguồn thực sự dùng preview feature, chạy class bằng runtime cùng release và bật preview:

~~~bash
java --enable-preview -cp out Main
~~~

Không dùng preview feature của JDK 24 rồi kỳ vọng class chạy trên Java 17. **--release 17** không thể bật preview feature của một release khác. Nếu sản phẩm cần tương thích với một Java release đã phát hành ổn định, tránh phụ thuộc preview feature trong artifact đó.

## 9. Những tùy chọn không nên ghép với --release

**--release** được thiết kế để kiểm tra API của một Java SE release cụ thể. Vì vậy, không thể kết hợp nó với **--source** hoặc **--target**:

~~~bash
javac --release 17 --source 17 Main.java
~~~

Lệnh trên bị từ chối với thông báo:

~~~text
error: option --source cannot be used together with --release
~~~

Tùy chọn **--release** cũng không cho phép dùng **--add-exports** để mở rộng các package của system module khi biên dịch theo một release cụ thể. Nếu mã phụ thuộc vào JDK internal API, hãy tìm API công khai thay thế và đánh giá lại thiết kế; đừng xem việc mở package nội bộ là giải pháp tương thích lâu dài.

Khi cần xem các ràng buộc chính xác của compiler đang dùng, kiểm tra:

~~~bash
javac --help
javac --help-extra
~~~

Tránh sao chép cấu hình từ build script cũ mà không kiểm tra. Các tùy chọn legacy như **-bootclasspath** hoặc **-profile** không phải cách chuẩn hiện nay để thiết lập API tương thích khi compiler hỗ trợ **--release**.

## 10. --release không thay thế việc chọn JDK toolchain

Có hai quyết định riêng:

1. Dùng JDK/compiler nào để thực hiện build?
2. Artifact phải tương thích với Java release nào?

Ví dụ, máy build dùng JDK 24 nhưng ứng dụng hỗ trợ Java 17:

~~~bash
javac --release 17 -d out src/Main.java
~~~

Lệnh này vẫn chạy compiler JDK 24. **--release 17** điều khiển mục tiêu biên dịch, không thay thế compiler bằng javac 17.

Nếu cần tái lập build bằng đúng compiler của JDK 17, hãy cấu hình toolchain riêng. Điều này có thể cần khi kiểm tra khác biệt compiler, annotation processor, plugin build hoặc hành vi đặc thù của nhà cung cấp.

Một cấu hình Maven phổ biến là đặt release trong compiler plugin:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Với Gradle Kotlin DSL, có thể đặt release cho JavaCompile:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Khi dùng build tool, kiểm tra toolchain đang thực thi compiler và xác nhận log build có truyền release target đúng như dự kiến.

## 11. Những gì --release không bảo đảm

Biên dịch thành công với **--release 17** là bằng chứng tốt về source, bytecode và API Java SE ở thời điểm compile. Tuy nhiên, nó không bảo đảm toàn bộ sản phẩm sẽ chạy được trên mọi runtime Java 17.

Các yếu tố vẫn cần kiểm tra:

- Dependency bên thứ ba có thể yêu cầu Java 21 hoặc phiên bản mới hơn.
- Reflection có thể tìm class/method theo tên và không được compiler kiểm tra đầy đủ.
- JNI/native library phải tương thích hệ điều hành, kiến trúc và runtime.
- Service provider, resource, cấu hình và plugin phải được đóng gói đúng.
- Hành vi TLS, charset, timezone, security provider và hệ điều hành có thể khác.
- Annotation processor hoặc plugin build chạy trong môi trường JDK đang dùng để build và cần được quản lý riêng.
- Mã nguồn được sinh động hoặc được nạp từ nơi khác có thể không đi qua cùng lần kiểm tra **--release**.

Vì vậy, build bằng **--release** cần đi cùng test trên runtime tối thiểu được hỗ trợ và kiểm tra dependency trong artifact phát hành.

## 12. Quy trình chọn release target

Trước khi cấu hình build, xác định phiên bản Java thấp nhất mà sản phẩm cam kết hỗ trợ. Sau đó:

1. Chọn release target đúng với cam kết hỗ trợ.
2. Kiểm tra compiler đang dùng có hỗ trợ release đó bằng **javac --help**.
3. Dùng **--release N** cho mọi module cần cùng baseline.
4. Build toàn bộ dependency nội bộ và kiểm tra dependency bên thứ ba.
5. Chạy test trên runtime Java N thực tế, không chỉ trên JDK mới ở máy build.
6. Kiểm tra class-file version bằng **javap -verbose** khi cần xác minh artifact.
7. Ghi release target trong build configuration để CI và máy phát triển dùng thống nhất.

Ví dụ ma trận kiểm tra:

| Mục tiêu | Cách xác minh |
|---|---|
| Ngôn ngữ Java đúng release | Biên dịch bằng **--release N** |
| Bytecode đúng release | **javap -verbose** kiểm tra major version |
| Không dùng API mới hơn | Thử biên dịch với **--release N** |
| Dependency tương thích | Kiểm tra metadata/bytecode và build/test trên runtime N |
| Ứng dụng chạy thật | Integration test trên JDK/runtime N |

## 13. Checklist trước khi phát hành

- [ ] Đã xác định phiên bản Java tối thiểu được hỗ trợ.
- [ ] Đã dùng **javac --release N** thay vì chỉ hạ **-source/-target**.
- [ ] Compiler hiện tại hỗ trợ release N.
- [ ] Không kết hợp **--release** với **--source** hoặc **--target**.
- [ ] Đã kiểm tra API Java SE mới hơn release mục tiêu bị từ chối.
- [ ] Đã kiểm tra bytecode version khi cần.
- [ ] Dependency và annotation processor đã được rà soát riêng.
- [ ] Không dựa vào preview feature nếu artifact cần chạy trên release khác.
- [ ] Đã chạy test trên runtime thấp nhất được hỗ trợ.
- [ ] Build tool/CI ghi nhận cùng release target.

## 14. Tài liệu tham khảo

- [Java SE 24 — javac compiler options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Java SE 24 API — Java Compiler](https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/module-summary.html)
- [JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247)
- [Java SE 24 — javap tool reference](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javap.html)
