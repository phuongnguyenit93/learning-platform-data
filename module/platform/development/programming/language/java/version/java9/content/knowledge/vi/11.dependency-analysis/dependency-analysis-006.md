# Chọn phiên bản khi phân tích JAR đa phiên bản

## Mục tiêu

Một thư viện Java có thể đóng gói nhiều implementation của cùng một class trong một JAR để tận dụng API hoặc tối ưu riêng cho từng thế hệ JDK. Cơ chế này được gọi là **Multi-Release JAR (MR-JAR)**. Khi chạy, JVM chọn entry phù hợp với phiên bản Java hiện tại. Khi phân tích dependency, công cụ như `jdeps` cũng cần biết đang xem JAR theo góc nhìn của phiên bản nào.

Nếu phân tích nhầm phiên bản, báo cáo có thể thiếu module dependency, ghi nhận dependency không được dùng ở runtime mục tiêu hoặc đưa ra kết luận sai về khả năng tương thích.

Sau bài này, bạn có thể:

- Nhận diện một MR-JAR qua manifest và cấu trúc `META-INF/versions`.
- Giải thích quy tắc chọn entry theo phiên bản runtime.
- Tạo MR-JAR bằng `jar --release`.
- Chọn đúng góc nhìn khi dùng `jdeps --multi-release` và `javap --multi-release`.
- Kiểm tra tính nhất quán API bằng `jar --validate`.
- Đối chiếu dependency của base view với dependency của một runtime cụ thể.
- Tránh các lỗi thường gặp khi đóng gói, phân tích và phát hành MR-JAR.

Ví dụ được kiểm tra bằng JDK 24.0.2; phần mã nguồn nền tảng dùng `--release 9` và implementation thay thế dùng `--release 17`.

## 1. Multi-Release JAR là gì?

MR-JAR là một file JAR có thể chứa các entry thay thế theo phiên bản Java. Cùng một đường dẫn logic có thể có bản cơ sở ở root JAR và một hoặc nhiều bản nằm trong các thư mục phiên bản.

Ví dụ:

~~~text
demo-mr.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── demo/RuntimeFlavor.class
│       ├── 17/
│       │   └── demo/RuntimeFlavor.class
│       └── 21/
│           └── demo/RuntimeFlavor.class
└── demo/
    ├── Main.class
    └── RuntimeFlavor.class
~~~

Các entry ở root là **base version**. Các entry bên dưới `META-INF/versions/N/` là phiên bản thay thế dành cho Java feature release N.

MR-JAR cho phép thư viện duy trì một artifact duy nhất trong khi:

- Giữ implementation cơ sở cho các runtime cũ hơn.
- Dùng API mới của JDK trong implementation dành cho runtime mới.
- Tối ưu code theo khả năng của một thế hệ JDK.
- Cung cấp resource hoặc metadata khác nhau theo runtime khi cần.

MR-JAR được hỗ trợ từ Java 9. Các thư mục phiên bản hợp lệ bắt đầu từ `9`; tên thư mục là số feature release, ví dụ `9`, `11`, `17`, `21`, không phải cách viết cũ như `1.8`.

## 2. Manifest quyết định JAR có phải MR-JAR hay không

Manifest chính của JAR phải có main attribute:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Attribute `Multi-Release: true` là điều kiện để runtime áp dụng quy tắc chọn entry đa phiên bản.

Nếu manifest không có attribute này hoặc giá trị không phải `true`, các entry trong `META-INF/versions` không được dùng làm bản thay thế khi nạp class. Runtime sử dụng entry ở root như với JAR thông thường.

Điều này rất quan trọng: chỉ tạo thư mục `META-INF/versions/17` trong JAR chưa đủ để tạo MR-JAR.

Khi dùng JDK `jar` tool với tùy chọn `--release N` để thêm versioned entries, công cụ tự thiết lập manifest attribute cần thiết. Nếu đóng gói bằng build tool hoặc công cụ ZIP khác, hãy kiểm tra manifest sau khi tạo artifact và đặt attribute rõ ràng.

Có thể kiểm tra manifest bằng:

~~~bash
jar --extract --file demo-mr.jar META-INF/MANIFEST.MF
~~~

Đọc file `META-INF/MANIFEST.MF` vừa giải nén và xác nhận có `Multi-Release: true` trong main section. Không đặt attribute này trong section riêng của một entry.

## 3. Runtime chọn entry như thế nào?

Khi runtime cần đọc một class hoặc resource có tên logic, JAR multi-release sẽ tìm bản phù hợp theo feature version của runtime:

1. Xác định feature version hiện tại của Java runtime.
2. Tìm versioned entry có số phiên bản cao nhất không lớn hơn runtime version.
3. Nếu tìm thấy, dùng entry đó.
4. Nếu không có versioned entry phù hợp, dùng entry base ở root JAR.
5. Nếu JAR không có `Multi-Release: true`, bỏ qua cơ chế thay thế và dùng entry base.

Ví dụ JAR có base, Java 9, Java 17 và Java 21:

| Runtime | Entry được chọn |
|---|---|
| Java 8 | Base entry, nếu base bytecode tương thích Java 8 |
| Java 9 | Entry trong `versions/9`, nếu có |
| Java 11 | Entry `versions/9`, nếu không có bản mới hơn phù hợp |
| Java 17 | Entry `versions/17` |
| Java 19 | Entry `versions/17` |
| Java 21 | Entry `versions/21` |
| Java 24 | Entry `versions/21` |

MR-JAR có thể được đọc như JAR thông thường trên Java 8; runtime cũ bỏ qua các versioned entries. Khả năng chạy trên Java 8 phụ thuộc vào việc base classes có được biên dịch tương thích Java 8 hay không. Ví dụ thực hành ở bài này biên dịch base bằng `--release 9`, vì vậy ví dụ có runtime tối thiểu là Java 9. Nếu thư viện cần hỗ trợ Java 8, hãy biên dịch base bằng `--release 8`; các thư mục versioned vẫn bắt đầu từ Java 9.

### 3.1. Chọn theo từng entry, không chọn nguyên một JAR con

MR-JAR không phải tập hợp các JAR độc lập để runtime chọn một file. Runtime chọn entry theo đường dẫn logic. Một số class có thể được thay thế ở Java 17 trong khi những class khác tiếp tục lấy từ base.

Ví dụ, nếu chỉ `demo/RuntimeFlavor.class` có bản ở `versions/17`, còn `demo/Main.class` chỉ có ở root, Java 17 sẽ nạp Main từ base và RuntimeFlavor từ bản Java 17.

Các resource cũng có thể có bản theo phiên bản. Vì vậy, khi phân tích resource hoặc service configuration, hãy nhớ rằng cơ chế multi-release áp dụng cho việc tra cứu entry trong JAR, không chỉ riêng bytecode class.

### 3.2. Phiên bản biên dịch và phiên bản chọn lúc chạy là hai việc khác nhau

`javac --release 17` biên dịch source theo ngôn ngữ, class-file target và API nền tảng của Java 17.

`jar --release 17` đặt các file tiếp theo vào `META-INF/versions/17/`.

Hai tùy chọn có tên giống nhau nhưng phục vụ hai công cụ và hai mục đích khác nhau:

- Dùng `javac --release N` để tạo bytecode phù hợp với release N.
- Dùng `jar --release N` để đóng gói entry vào thư mục versioned N.

Versioned class chỉ được chọn khi runtime có feature version từ N trở lên và entry đó là bản phù hợp cao nhất.

## 4. Phân tích dependency phải chọn đúng góc nhìn runtime

Một MR-JAR có thể chứa dependency khác nhau giữa base và các bản thay thế. Ví dụ implementation base chỉ dùng `java.base`, còn implementation Java 17 dùng thêm `java.net.http`.

Nếu ứng dụng triển khai trên Java 17 nhưng phân tích JAR theo base view, báo cáo có thể bỏ sót `java.net.http`. Khi tạo runtime image bằng `jlink`, việc bỏ sót module cần thiết có thể làm ứng dụng chạy thất bại.

Ngược lại, nếu chỉ phân tích view mới nhất trong khi ứng dụng vẫn phải chạy trên Java cũ, báo cáo có thể đưa ra dependency không xuất hiện ở runtime cũ.

Quy tắc thực hành: **phiên bản được chọn cho phân tích phải khớp với runtime mục tiêu của lần triển khai đang đánh giá**.

## 5. Dùng jdeps --multi-release

`jdeps` phân tích dependency của class và JAR. Tùy chọn `--multi-release` chọn phiên bản MR-JAR được dùng khi phân tích.

Cú pháp:

~~~bash
jdeps --multi-release base --print-module-deps library.jar
~~~

Phân tích base view:

~~~bash
jdeps --multi-release base --print-module-deps demo-mr.jar
~~~

Phân tích góc nhìn Java 17:

~~~bash
jdeps --multi-release 17 --print-module-deps demo-mr.jar
~~~

Giá trị của `--multi-release` là `base` hoặc một số nguyên feature version từ 9 trở lên. Có thể dùng cùng các tùy chọn khác của `jdeps`, chẳng hạn:

~~~bash
jdeps --multi-release 17 --verbose:class demo-mr.jar
~~~

Hoặc lấy danh sách module dependency:

~~~bash
jdeps --multi-release 17 --print-module-deps demo-mr.jar
~~~

`--print-module-deps` tạo danh sách module phân tách bằng dấu phẩy, có thể dùng làm đầu vào cho `jlink --add-modules`. Hãy chọn cùng release mà runtime image hoặc môi trường triển khai cần hỗ trợ.

### 5.1. Chọn release khi JDK phân tích mới hơn runtime mục tiêu

Có thể chạy `jdeps` bằng JDK 24 nhưng phân tích view Java 17:

~~~bash
jdeps --multi-release 17 --print-module-deps demo-mr.jar
~~~

Phiên bản JDK đang chạy công cụ và phiên bản MR-JAR được chọn là hai thông tin riêng. Tùy chọn `--multi-release 17` yêu cầu công cụ phân tích view Java 17 ngay cả khi executable `jdeps` thuộc JDK mới hơn.

Để báo cáo có thể tái lập, ghi lại:

- Phiên bản JDK chạy công cụ.
- Giá trị `--multi-release` đã chọn.
- Tên và phiên bản artifact được phân tích.
- Các dependency ngoài JDK được cung cấp qua class path hoặc module path.
- Runtime feature version mà kết quả hướng tới.

Không bỏ qua tùy chọn này trong pipeline nếu một dependency có thể là MR-JAR.

## 6. Dùng javap --multi-release để kiểm tra class được chọn

`javap` hiển thị signature và bytecode của class. Tùy chọn `--multi-release N` cho phép chọn view của MR-JAR khi đọc class trên class path.

Xem base view bằng feature release 9:

~~~bash
javap --multi-release 9 -classpath demo-mr.jar -c demo.RuntimeFlavor
~~~

Xem implementation dành cho Java 17:

~~~bash
javap --multi-release 17 -classpath demo-mr.jar -c demo.RuntimeFlavor
~~~

Với `javap`, dùng một số release cụ thể từ 9 trở lên. Để xem class base, chọn 9; nếu JAR không có versioned entry cho Java 9, công cụ sẽ hiển thị base entry.

Tùy chọn `-c` hiển thị bytecode. Có thể dùng `-p` để xem cả member không public, `-s` để xem descriptor hoặc `-verbose` để kiểm tra thêm metadata.

Ví dụ:

~~~bash
javap --multi-release 17 -classpath demo-mr.jar -p -c demo.RuntimeFlavor
~~~

Nếu class Java 17 có lệnh gọi `java.net.http.HttpClient`, bytecode view Java 17 sẽ thể hiện dependency đó. Base view không có lệnh gọi này.

## 7. Dùng jar --validate và jar --list

### 7.1. Xem cấu trúc archive

~~~bash
jar --list --file demo-mr.jar
~~~

Kiểm tra JAR có:

- Entry base ở root.
- Entry versioned dưới `META-INF/versions/N/`.
- Manifest ở `META-INF/MANIFEST.MF`.

Nếu chỉ thấy thư mục versioned mà không có manifest attribute, đừng kết luận runtime sẽ chọn các entry đó.

### 7.2. Kiểm tra API nhất quán

~~~bash
jar --validate --file demo-mr.jar
~~~

`jar --validate` kiểm tra tính nhất quán của API được export giữa các release trong MR-JAR. Đây là bước QA hữu ích khi một class có nhiều implementation theo phiên bản.

Mục tiêu của kiểu đóng gói này là thay implementation theo runtime trong khi consumer vẫn sử dụng hợp đồng API ổn định. Nếu public API của class bị thay đổi giữa base và versioned entry, client biên dịch theo một release có thể không còn tương thích với release khác.

Validation không thay thế kiểm thử chức năng, kiểm thử tương thích runtime hoặc phân tích dependency. Nó cũng không chứng minh rằng implementation mới không có lỗi logic.

## 8. Ví dụ hoàn chỉnh: một class có base và Java 17 implementation

Ta tạo một thư viện có hai phiên bản của `demo.RuntimeFlavor`:

- Base implementation trả về chuỗi `base`.
- Java 17 implementation dùng `HttpClient` và trả về tên module `java.net.http`.
- Public method `selected()` có cùng signature ở cả hai bản.

Cấu trúc source và build:

~~~text
mr-demo/
├── src/
│   ├── base/
│   │   └── demo/
│   │       ├── Main.java
│   │       └── RuntimeFlavor.java
│   └── v17/
│       └── demo/
│           └── RuntimeFlavor.java
└── build/
    ├── base/
    └── v17/
~~~

### 8.1. Base implementation

File `src/base/demo/RuntimeFlavor.java`:

~~~java
package demo;

public final class RuntimeFlavor {
    private RuntimeFlavor() {
    }

    public static String selected() {
        return "base";
    }
}
~~~

File `src/base/demo/Main.java`:

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println(RuntimeFlavor.selected());
    }
}
~~~

Biên dịch base theo Java 9:

~~~bash
javac --release 9 -d build/base src/base/demo/RuntimeFlavor.java src/base/demo/Main.java
~~~

### 8.2. Java 17 implementation

File `src/v17/demo/RuntimeFlavor.java`:

~~~java
package demo;

import java.net.http.HttpClient;

public final class RuntimeFlavor {
    private RuntimeFlavor() {
    }

    public static String selected() {
        return "java17:" + HttpClient.class.getModule().getName();
    }
}
~~~

Biên dịch riêng implementation Java 17:

~~~bash
javac --release 17 -cp build/base -d build/v17 src/v17/demo/RuntimeFlavor.java
~~~

Method `selected()` giữ nguyên public signature. Bản Java 17 chỉ thay phần implementation và dùng API `java.net.http` đã có trong Java 11 trở lên.

### 8.3. Đóng gói MR-JAR

Tạo file `MANIFEST.MF`:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Đóng gói:

~~~bash
jar --create --file demo-mr.jar --manifest MANIFEST.MF -C build/base . --release 17 -C build/v17 demo/RuntimeFlavor.class
~~~

`-C build/base .` thêm các class base. `--release 17` đặt file tiếp theo vào `META-INF/versions/17/`. `-C build/v17 demo/RuntimeFlavor.class` thêm implementation Java 17.

Kiểm tra cấu trúc:

~~~bash
jar --list --file demo-mr.jar
~~~

Các entry quan trọng:

~~~text
META-INF/MANIFEST.MF
demo/Main.class
demo/RuntimeFlavor.class
META-INF/versions/17/demo/RuntimeFlavor.class
~~~

### 8.4. Chạy ứng dụng

~~~bash
java -cp demo-mr.jar demo.Main
~~~

Trên JDK 17 trở lên, nếu không có versioned entry mới hơn phù hợp, runtime chọn implementation Java 17.

Stdout trên JDK 17+:

~~~text
java17:java.net.http
~~~

Nếu chạy trên runtime có feature version 9 đến 16, runtime dùng base implementation:

~~~text
base
~~~

Nếu manifest không có `Multi-Release: true`, runtime cũng dùng base implementation dù entry Java 17 vẫn còn trong archive.

### 8.5. Đối chiếu dependency theo release

Phân tích base:

~~~bash
jdeps --multi-release base --print-module-deps demo-mr.jar
~~~

Kết quả:

~~~text
java.base
~~~

Phân tích Java 17:

~~~bash
jdeps --multi-release 17 --print-module-deps demo-mr.jar
~~~

Kết quả:

~~~text
java.base,java.net.http
~~~

Kết quả cho thấy cùng một file JAR có dependency module khác nhau theo view được chọn. Nếu ứng dụng chạy trên Java 17 và sử dụng implementation Java 17, báo cáo base không đủ để xác định toàn bộ module cần thiết.

### 8.6. Xem bytecode của hai view

Base view:

~~~bash
javap --multi-release 9 -classpath demo-mr.jar -c demo.RuntimeFlavor
~~~

Trong bytecode, method `selected()` trả về hằng chuỗi `base`.

Java 17 view:

~~~bash
javap --multi-release 17 -classpath demo-mr.jar -c demo.RuntimeFlavor
~~~

Trong bytecode, method `selected()` tham chiếu đến `java/net/http/HttpClient`.

Cuối cùng kiểm tra tính nhất quán API:

~~~bash
jar --validate --file demo-mr.jar
~~~

Ví dụ này đã được chạy trên JDK 24.0.2. Kết quả runtime là `java17:java.net.http`; JAR không có manifest multi-release trả về `base`; `jdeps` cho base view trả về `java.base`, còn Java 17 view trả về `java.base,java.net.http`.

## 9. Module descriptor trong MR-JAR

Một MR-JAR cũng có thể cung cấp module descriptor theo phiên bản, ví dụ:

~~~text
META-INF/versions/9/module-info.class
~~~

Điều này cho phép cùng artifact có thể được nhìn nhận theo quy tắc module system trên runtime hỗ trợ JPMS. Khi phân tích một thư viện modular, hãy kiểm tra module descriptor trong đúng release view, đặc biệt khi descriptor chỉ xuất hiện ở thư mục versioned.

Các công cụ hữu ích:

~~~bash
jar --describe-module --file library.jar
jdeps --multi-release 17 --print-module-deps library.jar
~~~

Nếu JAR có versioned `module-info.class`, hãy dùng công cụ JDK phù hợp với release mục tiêu để xem descriptor và dependency. Đừng chỉ nhìn tên file hoặc manifest rồi suy ra module name.

## 10. Chọn phiên bản trong pipeline phân tích dependency

Một pipeline phân tích nên lấy runtime mục tiêu làm đầu vào thay vì mặc định dùng phiên bản mới nhất của JDK cài trên máy build.

Ví dụ ứng dụng triển khai trên Java 17:

~~~bash
jdeps --multi-release 17 --print-module-deps app.jar
jar --validate --file library-mr.jar
javap --multi-release 17 -classpath library-mr.jar -c demo.RuntimeFlavor
~~~

Nếu cùng artifact phải hỗ trợ cả Java 17 và Java 21, hãy chạy phân tích riêng cho từng view:

~~~bash
jdeps --multi-release 17 --print-module-deps library-mr.jar
jdeps --multi-release 21 --print-module-deps library-mr.jar
~~~

Lưu lại kết quả theo từng runtime. Nếu hai view có module dependency khác nhau, runtime image hoặc cấu hình module có thể cần được tạo riêng cho từng nền tảng triển khai.

Một bảng báo cáo nên ghi rõ:

| Trường | Ví dụ |
|---|---|
| Artifact | `library-mr.jar` |
| Runtime mục tiêu | Java 17 |
| Góc nhìn phân tích | `--multi-release 17` |
| Module dependency | `java.base,java.net.http` |
| Kiểm tra API | `jar --validate` |
| Class đã kiểm tra | `demo.RuntimeFlavor` |
| Công cụ/JDK phân tích | JDK 24.0.2 |

Nếu không ghi release được chọn, người review khó biết kết quả dependency phản ánh base hay implementation của runtime đang triển khai.

## 11. Lỗi thường gặp

### Có thư mục versions nhưng thiếu manifest attribute

Runtime không áp dụng cơ chế MR-JAR. Kiểm tra main manifest section và đảm bảo `Multi-Release: true`.

### Dùng sai số phiên bản thư mục

Thư mục phải dùng feature release từ 9 trở lên. Dùng `17`, không dùng `1.17` hoặc `1.8`.

### Phân tích base trong khi triển khai runtime mới

Báo cáo có thể bỏ sót dependency mà implementation mới sử dụng. Đặt `jdeps --multi-release N` theo runtime mục tiêu.

### Dùng góc nhìn mới nhất cho mọi môi trường

Nếu ứng dụng còn hỗ trợ runtime cũ, phân tích release mới nhất không đại diện cho các runtime đó. Chạy phân tích riêng cho từng release được hỗ trợ.

### Nhầm javac --release với jar --release

`javac --release` chọn API và bytecode target. `jar --release` chọn thư mục versioned trong archive. Cả hai có thể cần dùng trong cùng quy trình tạo MR-JAR.

### Cho rằng runtime luôn lấy entry có số lớn nhất

Runtime chỉ lấy versioned entry cao nhất không vượt quá feature version hiện tại. Entry dành cho Java 21 không được chọn trên Java 17.

### Quên kiểm tra tính nhất quán API

Versioned implementation phải duy trì hợp đồng public API phù hợp. Dùng `jar --validate` và kiểm thử tương thích để phát hiện sai khác.

### Nghĩ mọi dependency xuất hiện trong JAR đều được dùng

Một versioned entry có thể không được chọn trên runtime mục tiêu. Phân tích theo đúng release giúp tách dependency của base khỏi dependency của implementation đang chạy.

### Chỉ kiểm tra bằng cách chạy trên JDK build

JDK build có thể mới hơn runtime production. Dùng `jdeps --multi-release N` và `javap --multi-release N` để chọn view mục tiêu; nếu có thể, bổ sung chạy integration test trên đúng JDK production.

## 12. Checklist trước khi kết luận dependency

- [ ] Artifact có phải MR-JAR không?
- [ ] Manifest có main attribute `Multi-Release: true` không?
- [ ] Các versioned entry nằm đúng `META-INF/versions/N/` với N từ 9 trở lên không?
- [ ] Runtime mục tiêu có feature version nào?
- [ ] Entry được chọn cho class/resource quan trọng đã được xác định chưa?
- [ ] Đã chạy `jdeps --multi-release N` theo runtime mục tiêu chưa?
- [ ] Nếu cần base view, đã dùng `jdeps --multi-release base` chưa?
- [ ] Đã dùng `javap --multi-release N` để xác nhận implementation quan trọng chưa?
- [ ] Đã chạy `jar --validate` để kiểm tra API nhất quán chưa?
- [ ] Nếu có versioned `module-info.class`, đã kiểm tra module descriptor theo release chưa?
- [ ] Nếu hỗ trợ nhiều runtime, đã phân tích từng view riêng chưa?
- [ ] Báo cáo đã ghi rõ JDK chạy công cụ và release được chọn chưa?

## Tóm tắt

MR-JAR đóng gói base entry và các entry thay thế dưới `META-INF/versions/N/`; manifest phải có `Multi-Release: true`. Runtime chọn versioned entry cao nhất không vượt quá feature version hiện tại, nếu không có thì dùng base. Khi phân tích dependency, `jdeps --multi-release N` phải khớp runtime mục tiêu; dùng `base` khi cần xem implementation gốc. `javap --multi-release N` giúp kiểm tra bytecode được chọn, còn `jar --validate` kiểm tra tính nhất quán API giữa các release. Một file JAR có thể có module dependency khác nhau ở các view khác nhau, vì vậy báo cáo phải ghi rõ phiên bản được phân tích.

## Tài liệu tham khảo chính thức

- [JEP 238 — Multi-Release JAR Files](https://openjdk.org/jeps/238)
- [The JAR File Specification — Multi-Release JAR Files](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
- [The jar Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [The javap Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html)
- [Java SE 26 API — JarFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarFile.html)
