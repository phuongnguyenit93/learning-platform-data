# Target release trong javac

Khi phát triển ứng dụng Java, bạn có thể dùng JDK mới để biên dịch nhưng vẫn cần tạo chương trình chạy được trên một phiên bản Java cũ hơn. Ví dụ, nhóm phát triển dùng JDK 21 nhưng sản phẩm phải chạy trên Java 17 hoặc Java 8. Khi đó, **target release** xác định phiên bản Java tối thiểu mà bytecode và API nền tảng được biên dịch hướng tới.

Với `javac` hiện đại, lựa chọn nên dùng là `--release`. Tùy chọn này phối hợp ba yêu cầu: quy tắc ngôn ngữ Java, định dạng class file và tập API Java SE/JDK của phiên bản đích. Chỉ hạ phiên bản bytecode chưa đủ để bảo đảm tương thích.

## 1. Target release là gì?

Một bản phát hành Java có thể được nhìn qua ba khía cạnh liên quan đến biên dịch:

1. **Source level:** cú pháp và tính năng ngôn ngữ mà compiler cho phép trong mã nguồn.
2. **Class-file target:** định dạng bytecode được ghi vào các tệp `.class`, để JVM của phiên bản đích có thể đọc.
3. **Platform API:** các lớp, interface và phương thức của Java SE/JDK mà mã nguồn được phép sử dụng.

Ví dụ, nếu ứng dụng phải chạy trên Java 17 thì cần:

- Viết mã nguồn trong phạm vi ngôn ngữ Java 17.
- Tạo class file tương thích với Java 17.
- Chỉ sử dụng API nền tảng đã có trong Java 17.

Nếu chỉ tạo bytecode theo Java 17 nhưng lại gọi một phương thức chỉ được thêm vào Java 21, chương trình vẫn có thể biên dịch trên JDK 21 nhưng gặp lỗi khi chạy trên Java 17, thường là `NoSuchMethodError` hoặc `NoClassDefFoundError`.

## 2. Dùng javac --release

Tùy chọn `--release N` yêu cầu compiler biên dịch theo phiên bản Java SE `N` được chỉ định:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Lệnh trên có nghĩa:

- Dùng quy tắc ngôn ngữ Java 17.
- Sinh class file hướng tới Java 17.
- Biên dịch dựa trên tập API Java SE/JDK công khai được hỗ trợ ở Java 17.

Có thể kết hợp với các tùy chọn biên dịch thông thường:

~~~bash
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Main.java
~~~

Ý nghĩa:

| Tùy chọn | Công dụng |
|---|---|
| `--release 17` | Chọn nền tảng Java 17 làm phiên bản đích |
| `-encoding UTF-8` | Đọc mã nguồn theo UTF-8 |
| `-Xlint:all` | Bật các nhóm cảnh báo bổ sung |
| `-d out` | Đưa class file vào thư mục `out` |

Có thể kiểm tra các release mà compiler hiện tại hỗ trợ bằng:

~~~bash
javac --help
~~~

Danh sách hỗ trợ phụ thuộc phiên bản JDK đang dùng. Một compiler chỉ hỗ trợ release hiện tại và một số release cũ hơn; JDK cũ không thể biên dịch hướng tới một release tương lai mà nó chưa biết.

`--release` được bổ sung từ JDK 9. Nếu đang dùng compiler JDK 8 trở xuống, tùy chọn này không có sẵn.

## 3. Phân biệt --release, -source và -target

Ba tùy chọn này liên quan đến nhau nhưng có phạm vi khác nhau.

| Tùy chọn | Điều khiển | Không tự bảo đảm |
|---|---|---|
| `-source N` | Quy tắc cú pháp/tính năng ngôn ngữ của Java N | Định dạng bytecode và tập API của Java N |
| `-target N` | Phiên bản định dạng class file | Tập API mà mã nguồn sử dụng |
| `--release N` | Source level, class-file target và API nền tảng của release N | Tính tương thích của thư viện bên ngoài hoặc hành vi lúc chạy |

Ví dụ với hai tùy chọn cũ:

~~~bash
javac -source 17 -target 17 -d out src/com/example/Main.java
~~~

Compiler kiểm tra cú pháp Java 17 và sinh class file mục tiêu Java 17. Tuy nhiên, nếu compiler đang chạy trên JDK 21, các API của JDK 21 vẫn có thể xuất hiện trong môi trường biên dịch trừ khi bạn chỉ định đúng platform classes.

Khi dùng `-source`/`-target` riêng:

- Với nền tảng Java 8 trở xuống, cần cung cấp platform classes tương ứng qua nhóm tùy chọn boot class path.
- Với Java 9 trở lên, có thể dùng `--system` để chỉ định hệ thống module của một JDK phù hợp.

Đó là lý do quy trình hiện đại thường ưu tiên `--release`: compiler tự chọn tập API tương ứng, tránh tình trạng bytecode cũ nhưng tham chiếu API mới.

Không kết hợp `--release` với `-source` hoặc `-target` trong cùng một lần biên dịch. Đây là các cách chọn phiên bản đích thay thế nhau.

## 4. Ví dụ: API mới có thể phá tương thích

Xét tệp `TargetReleaseDemo.java`:

~~~java
import java.util.List;

public class TargetReleaseDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Java", "JDK");
        System.out.println(String.join(", ", names));
    }
}
~~~

Phương thức `List.of` được giới thiệu trong Java 9.

### 4.1. Biên dịch hướng tới Java 8

~~~bash
javac --release 8 -d out-8 TargetReleaseDemo.java
~~~

Compiler báo lỗi vì `List.of` không thuộc API Java 8. Đây là kết quả mong muốn: lỗi được phát hiện ngay khi biên dịch thay vì đợi chương trình chạy trên Java 8.

### 4.2. Biên dịch hướng tới Java 11

~~~bash
javac --release 11 -d out-11 TargetReleaseDemo.java
java -cp out-11 TargetReleaseDemo
~~~

Kết quả:

~~~text
Java, JDK
~~~

Java 11 có API `List.of` nên mã nguồn này hợp lệ. Class file được tạo hướng tới Java 11.

### 4.3. Vì sao chỉ dùng -source và -target có thể chưa đủ?

Với compiler JDK 21, thử:

~~~bash
javac -source 8 -target 8 -d out-legacy TargetReleaseDemo.java
~~~

Mã nguồn có thể được chấp nhận vì `-source 8` chỉ giới hạn cú pháp, trong khi compiler vẫn nhìn thấy API của JDK 21. Compiler có thể sinh class file mục tiêu Java 8 nhưng class file đó tham chiếu `List.of`.

Khi chạy trên Java 8, JVM có thể nạp class file nhưng không tìm thấy phương thức `List.of` trong lớp `java.util.List`. Lỗi chỉ xuất hiện lúc liên kết hoặc thực thi. Cảnh báo về bootstrap class path cũng là dấu hiệu cho thấy môi trường API cũ chưa được cung cấp.

Dùng `--release 8` sẽ chặn tham chiếu API này ngay từ bước biên dịch.

## 5. Phiên bản class file và cách kiểm tra

Mỗi thế hệ Java có một class-file major version. Một số mốc thường gặp:

| Java release | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Có thể kiểm tra class file bằng `javap`:

~~~bash
javap -verbose -classpath out-11 TargetReleaseDemo
~~~

Trong phần đầu ra, tìm dòng:

~~~text
major version: 55
~~~

Major version 55 tương ứng với Java 11. Đây là cách xác nhận định dạng class file mà compiler thực sự tạo ra.

Nếu một JVM quá cũ cố chạy class file có major version mới hơn khả năng hỗ trợ, nó có thể báo `UnsupportedClassVersionError`. Lỗi này khác với `NoSuchMethodError`:

- `UnsupportedClassVersionError`: JVM không đọc được phiên bản class file.
- `NoSuchMethodError`: class file được nạp nhưng khi liên kết/thực thi, phương thức được tham chiếu không tồn tại trong lớp đang được nạp.

## 6. --release giới hạn API nào?

Khi biên dịch với `--release`, `javac` sử dụng API Java SE và JDK được hỗ trợ của release đã chọn. Vì vậy, mã nguồn không thể vô tình gọi một API nền tảng mới hơn chỉ vì JDK compiler đang cài đặt là bản mới.

Điều này hữu ích khi:

- Duy trì ứng dụng chạy trên nhiều phiên bản Java.
- Xây thư viện dùng chung cho nhiều dự án.
- Nâng cấp JDK biên dịch nhưng chưa nâng phiên bản runtime sản phẩm.
- Phát hiện sớm việc sử dụng API mới trong pull request hoặc pipeline build.

Tuy nhiên, `--release` không giới hạn API của mọi thư viện bên ngoài. Nếu classpath có thư viện chỉ hỗ trợ Java 21, việc biên dịch ứng dụng với `--release 17` không tự làm thư viện đó tương thích Java 17.

Bạn vẫn cần kiểm tra:

- Phiên bản bytecode của dependency.
- Phiên bản Java tối thiểu mà nhà cung cấp thư viện công bố.
- Các API mà thư viện gọi khi chạy.
- Reflection, service loading, JNI và các thành phần được nạp động.
- Công cụ build, annotation processor và plugin có yêu cầu JDK riêng hay không.

Ngoài ra, `--release` chỉ cho phép dùng API được tài liệu hóa cho release đó; không thể dùng các tùy chọn phá vỡ đóng gói module để truy cập API nội bộ của JDK như thể chúng là API công khai được hỗ trợ.

## 7. Chọn release theo yêu cầu dự án

Không nên chọn release chỉ vì đó là JDK mới nhất trên máy. Hãy bắt đầu từ môi trường triển khai thực tế.

| Tình huống | Cách chọn |
|---|---|
| Ứng dụng mới, runtime thống nhất Java 21 | Dùng `--release 21` |
| Dự án biên dịch bằng JDK 21 nhưng server chạy Java 17 | Dùng `--release 17` |
| Thư viện phải hỗ trợ Java 8 | Dùng `--release 8` và bảo đảm dependency cũng hỗ trợ Java 8 |
| Dự án cần Java 11 | Dùng `--release 11` và kiểm thử trên runtime Java 11 |
| Muốn dùng API mới hơn release đang hỗ trợ | Nâng runtime tối thiểu hoặc thay API bằng lựa chọn tương thích |

Ví dụ, nếu server production dùng Java 17 nhưng máy phát triển đã cài JDK 21:

~~~bash
java --version
javac --version
javac --release 17 -d out src/com/example/Main.java
~~~

Hai lệnh đầu có thể hiển thị Java 21. Điều đó không mâu thuẫn với việc compiler sinh bytecode/API mục tiêu Java 17.

## 8. Quy trình kiểm tra tương thích

Một lần biên dịch thành công chưa đủ để chứng minh ứng dụng sẽ chạy ổn định trên release đích. Có thể dùng quy trình sau:

1. **Xác định runtime tối thiểu:** hỏi môi trường triển khai hoặc đọc yêu cầu sản phẩm để biết Java 8, 11, 17, 21 hay phiên bản khác.
2. **Chọn compiler phù hợp:** dùng JDK có thể hỗ trợ release đích; compiler mới thường có thể biên dịch hướng tới một số release cũ.
3. **Biên dịch bằng --release:** ví dụ `javac --release 17 -d out ...`.
4. **Kiểm tra bytecode:** dùng `javap -verbose` và đối chiếu major version.
5. **Kiểm tra dependency:** xác nhận thư viện ngoài hỗ trợ đúng phiên bản Java tối thiểu.
6. **Chạy test trên runtime đích:** dùng chính JDK/JRE tương ứng hoặc môi trường container có đúng phiên bản.
7. **Kiểm tra pipeline:** bảo đảm IDE, Maven/Gradle, CI và script phát hành cùng dùng cấu hình release thống nhất.

Nên kiểm thử trên phiên bản runtime thực tế thấp nhất mà sản phẩm cam kết hỗ trợ. Chạy trên JDK mới hơn có thể che giấu lỗi thiếu API vì runtime mới vẫn còn nhiều API cũ.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `invalid source release` hoặc release không được hỗ trợ | JDK compiler quá cũ hoặc release không nằm trong danh sách hỗ trợ | Chạy `javac --version` và `javac --help`; cài JDK phù hợp |
| `option --release not allowed with target` | Dùng đồng thời `--release` với `-target` hoặc `-source` | Chọn một cơ chế duy nhất; ưu tiên `--release` |
| `cannot find symbol` khi dùng API mới | API không tồn tại trong release đích | Thay bằng API tương thích hoặc nâng release |
| `UnsupportedClassVersionError` | Runtime cũ hơn class-file version | Biên dịch bằng release phù hợp hoặc nâng runtime |
| `NoSuchMethodError` | Dependency/runtime thiếu phương thức mà bytecode tham chiếu | Kiểm tra API thực tế và phiên bản dependency; chạy test trên runtime đích |
| Chạy trên máy phát triển được nhưng production lỗi | Máy phát triển dùng runtime mới hơn hoặc classpath khác | Kiểm thử trong môi trường giống production |
| Build local và CI cho kết quả khác nhau | JDK compiler hoặc cấu hình release không đồng nhất | Khóa toolchain và cấu hình build trong CI |

## 10. Một số lưu ý khi sử dụng

- Dùng `--release` cho dự án hiện đại cần hỗ trợ phiên bản Java cũ hơn.
- Không nhầm phiên bản JDK dùng để chạy compiler với target release của sản phẩm.
- Không dùng riêng `-target` để kết luận ứng dụng tương thích API với runtime cũ.
- Không đặt `--release` cùng `-source` hoặc `-target`.
- Xác nhận release hỗ trợ bằng `javac --help` thay vì giả định mọi JDK đều hỗ trợ mọi release cũ.
- Kiểm tra dependency và chạy test trên runtime tối thiểu.
- Đọc `javap -verbose` khi cần xác minh major version thực tế.
- Với ứng dụng dùng preview features, phải tuân thủ riêng quy tắc `--enable-preview` và phiên bản runtime tương ứng; preview API không phải hợp đồng tương thích dài hạn.

## 11. Ghi nhớ

`--release` là lựa chọn quan trọng để kiểm soát tương thích khi dùng `javac`. Nó đồng thời chọn quy tắc ngôn ngữ, class-file version và API nền tảng của release đích. `-source` chỉ chọn source level; `-target` chỉ chọn định dạng class file. Kết hợp source/target mà không cung cấp platform classes phù hợp có thể tạo bytecode cũ nhưng vẫn phụ thuộc API mới.

Biên dịch với đúng release, xác minh class file, kiểm tra dependency và chạy test trên runtime tối thiểu là các bước cần thiết để kiểm soát tương thích Java một cách đáng tin cậy.

Tài liệu tham khảo: [The javac Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), các mục `--release`, `--source`, `--target` và *Compiling for Earlier Releases of the Platform*.
