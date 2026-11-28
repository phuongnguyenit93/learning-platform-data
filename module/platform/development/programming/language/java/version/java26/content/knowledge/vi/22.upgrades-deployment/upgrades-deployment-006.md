# Không tái sử dụng class file preview của phiên bản JDK khác

Một class file được biên dịch có dùng preview feature chỉ dành cho đúng phiên bản Java SE đã định nghĩa preview đó. Ví dụ, class file preview tạo bởi JDK 26 có version `70.65535`; JVM Java 26 chỉ tải được file này khi bật preview, còn JVM Java 27 sẽ từ chối file đó ngay cả khi chạy với `--enable-preview`. Cờ `--enable-preview` của Java 27 chỉ bật preview feature của Java 27, không mở khóa class file preview của Java 26.

Trong module JAVA_VERSION_JAVA26, quy tắc này là một phần của quy trình nâng cấp và triển khai các cải tiến về HTTP, pattern matching, structured concurrency, Vector API, bảo mật và tối ưu JVM. Bất kỳ dependency nào dùng preview hoặc incubator cũng cần được đánh giá theo đúng lifecycle và runtime đích trước khi đưa vào artifact triển khai.

Quy tắc này áp dụng cho class file trong ứng dụng, thư viện phụ thuộc, plugin, annotation processor và class được đóng gói trong JAR. Khi chuyển JDK, cần xác định các dependency có class file preview, biên dịch lại từ source bằng đúng JDK đích và kiểm thử toàn bộ runtime. Nếu muốn artifact chạy ổn định trên nhiều JDK, hãy dùng API đã final và biên dịch không bật preview. [Java 26 JVMS, mục 4.1](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html) · [Java 26 JVMS, mục 1.5](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-1.html) · [JEP 12 — Preview Features](https://openjdk.org/jeps/12).

## 1. Class file version gồm major và minor

Java compiler không đóng gói mã nguồn Java vào `.class`. Nó tạo một class file có header, constant pool, field, method, bytecode và metadata. Hai trường version trong header cho JVM biết định dạng class file và release Java mà file phụ thuộc:

- `major_version`: phiên bản định dạng class file chính.
- `minor_version`: phiên bản phụ; với Java SE 12 trở lên, giá trị `65535` là dấu hiệu class file phụ thuộc preview features của release tương ứng.

Java 26 sử dụng major version `70`. Bảng sau cho thấy khác biệt quan trọng:

| Nguồn biên dịch | Class file version | Ý nghĩa |
|---|---:|---|
| Java 26, không phụ thuộc preview | `70.0` | Class file Java 26 thông thường. |
| Java 26, phụ thuộc preview | `70.65535` | Class file dùng preview features của Java 26. |
| Java 27, không phụ thuộc preview | `71.0` | Class file Java 27 thông thường. |
| Java 27, phụ thuộc preview | `71.65535` | Class file dùng preview features của Java 27. |

Đối với major version từ 56 trở lên, minor version hợp lệ là `0` hoặc `65535`. JDK 26 hỗ trợ class file major version từ 45 đến 70. Một class file `70.65535` chỉ được tải trên JVM Java 26 khi preview được bật. JVM Java 26 không tải class file preview của Java 25; JVM Java 27 cũng không tải class file preview của Java 26. [JVMS 26 — The `ClassFile` Structure](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html).

## 2. Vì sao class file preview gắn với một release?

Preview feature là tính năng đã có thiết kế và implementation để developer thử nghiệm, nhưng chưa được cam kết là API/ngôn ngữ ổn định. Qua từng release, feature có thể:

- Được sửa đổi và tiếp tục preview.
- Được hoàn thiện thành tính năng chính thức.
- Bị rút lại hoặc loại bỏ.

Do đó, bytecode hoặc metadata được tạo dựa trên preview feature của release N có thể không còn tương thích với release N+1. JVM dùng cặp major/minor version để nhận biết sự phụ thuộc này, thay vì đoán xem class file có thật sự gọi một lệnh preview cụ thể hay không.

JVM áp dụng hai điều kiện cho class file preview của release hiện tại:

1. Class file phải thuộc đúng release của JVM.
2. Preview features phải được bật ở runtime.

Class file preview của release khác bị từ chối, bất kể `--enable-preview` có xuất hiện trên command line. Đây là quy tắc của định dạng class file và JVM, không phải tùy chọn riêng của Maven, Gradle hay IDE. [JVMS 26 — Restrictions on the Use of Preview Features](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-1.html) · [Java 26 `ClassFileVersion`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/ClassFileVersion.html).

Minor version `65535` không phải bộ dò xem bytecode có chứa một instruction preview hay không. Compiler có thể phải đánh dấu class file phụ thuộc preview của release ngay cả khi class file không dùng preview VM feature; ví dụ source của class sử dụng preview language feature. Vì vậy, không thể bỏ marker bằng cách cho rằng một class “trông như bytecode Java thường” hoặc không gọi trực tiếp một API preview.

### Preview không phải một chế độ tương thích ngược

`--enable-preview` không có nghĩa là JVM chấp nhận mọi class file preview từ các JDK trước. Nó chỉ cho phép sử dụng preview features thuộc chính release đang chạy. JVM không có tùy chọn kiểu `--enable-preview=25` để chạy class file preview Java 25 trên Java 26.

| Runtime | Class file `70.65535` từ Java 26 | Class file `71.65535` từ Java 27 |
|---|---|---|
| Java 26, không bật preview | Từ chối | Từ chối |
| Java 26, bật preview | Cho phép tải | Từ chối |
| Java 27, không bật preview | Từ chối vì preview của release khác | Từ chối vì preview đang tắt |
| Java 27, bật preview | Từ chối vì preview của release khác | Cho phép tải |

Các class file thông thường có minor version `0` tuân theo quy tắc tương thích định dạng khác. JDK mới thường hỗ trợ class file major version cũ; tuy nhiên, việc tải được class file không đảm bảo các API mà ứng dụng gọi vẫn tồn tại hoặc có hành vi giống nhau. Cần phân biệt tương thích định dạng bytecode với tương thích API và hành vi runtime.

## 3. Ví dụ preview feature trong Java 26

Java 26 có preview feature **Primitive Types in Patterns, `instanceof`, and `switch`**, được mô tả trong JEP 530 (Fourth Preview). Feature này mở rộng pattern matching để làm việc với primitive types và mở rộng kiểm tra chuyển đổi an toàn. Tại Java 26, đây vẫn là preview, chưa phải cú pháp Java ổn định. [Java 26 Language Changes](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html) · [JEP 530 — Fourth Preview](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html).

Ví dụ minh họa một đoạn code dùng primitive pattern của Java 26:

```java
public class PrimitivePatternExample {
    static String describe(Object value) {
        return switch (value) {
            case int number when number >= 0 -> "non-negative int: " + number;
            case int number -> "negative int: " + number;
            case null -> "null";
            default -> "other value";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(42));
        System.out.println(describe(-7));
    }
}
```

Đoạn code này cần compiler và runtime Java 26 bật preview. Không thể lấy file `PrimitivePatternExample.class` đã biên dịch bằng Java 26 rồi đưa vào ứng dụng chạy Java 27 với hy vọng `--enable-preview` của Java 27 sẽ chấp nhận nó. Nếu feature được preview lại trong release sau, hãy biên dịch source bằng compiler của release đó và xem lại thay đổi đặc tả, cảnh báo và kiểm thử.

## 4. Biên dịch và chạy preview đúng release

Khi thử nghiệm preview của Java 26, dùng JDK 26 ở cả hai bước:

```bash
# Biên dịch bằng javac 26, bật preview của Java 26.
javac --release 26 --enable-preview \
      -d out-preview-26 \
      src/PrimitivePatternExample.java

# Chạy bằng java 26, bật preview của Java 26.
java --enable-preview \
     -cp out-preview-26 \
     PrimitivePatternExample
```

`--release 26` yêu cầu compiler dùng quy tắc ngôn ngữ, class file target và API của Java 26. `--enable-preview` bật preview feature ở compile time. Runtime cũng phải nhận `--enable-preview`; chỉ bật ở compiler là chưa đủ.

Nếu đóng gói thành executable JAR, runtime flag vẫn cần được truyền khi khởi chạy:

```bash
java --enable-preview -jar app-preview-26.jar
```

Với module:

```bash
java --enable-preview \
     --module-path mods-preview-26 \
     --module com.example.app/com.example.Main
```

Không bỏ cờ runtime chỉ vì file đã được biên dịch thành công. JVM mặc định tắt preview features, và class file có minor version `65535` sẽ không được tải nếu preview chưa được bật.

### Biên dịch code ổn định

Nếu code chỉ dùng API và ngôn ngữ đã final, không bật preview:

```bash
javac --release 26 -d out-stable src/main/java/com/example/Main.java
java -cp out-stable com.example.Main
```

Class file thông thường tạo bởi JDK 26 có version `70.0`. Một JDK mới hơn có thể hỗ trợ định dạng này; vẫn phải kiểm tra API dependency và hành vi ứng dụng trên runtime đích.

## 5. Không dùng `--release` cũ để giữ preview của release mới

`--release` không phải công cụ chuyển preview feature của một release sang release thấp hơn. Nếu source sử dụng preview feature Java 26, không thể dùng `--release 25` để tạo class file preview Java 25. Preview feature thuộc Java 26 chỉ có ý nghĩa với compiler/runtime Java 26.

Khi cần chạy trên Java 25, có hai hướng:

1. Viết lại đoạn dùng preview bằng cú pháp/API đã ổn định và tồn tại trong Java 25, sau đó biên dịch với `--release 25`.
2. Nâng baseline runtime lên Java 26, biên dịch và chạy preview đúng release nếu tổ chức chấp nhận rủi ro preview.

Ví dụ baseline Java 25 ổn định:

```bash
# Dùng JDK có hỗ trợ --release 25; không bật preview.
javac --release 25 -d out-java25 src/main/java/com/example/Main.java
```

Lệnh này chỉ thành công nếu source không dùng cú pháp preview và không tham chiếu API chỉ có từ Java 26 trở lên. `--release` cũng giới hạn tập API được phép dùng, không chỉ thay major version trong class file. [JDK 26 `javac` — `--release`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html).

## 6. Dependency cũng có thể mang class file preview

Không chỉ class do project tự biên dịch mới có thể phụ thuộc preview. Một dependency JAR có thể chứa class file được biên dịch với preview của JDK khác. Ví dụ:

```text
application.jar
  com/example/Main.class                 70.0

vendor-library.jar
  com/vendor/Parser.class                70.65535
```

Ứng dụng có thể biên dịch thành công nếu compiler chưa cần nạp class preview đó trong đường đi biên dịch đang xét. Khi runtime lần đầu nạp `com.vendor.Parser`, JVM có thể từ chối class file vì preview marker không khớp release hoặc preview chưa được bật.

Các nguồn class preview thường gặp:

- Thư viện nội bộ thử nghiệm preview feature.
- Plugin hoặc extension được build bằng JDK preview khác.
- Annotation processor, compiler plugin hoặc code generator phát sinh class file preview.
- JAR được cache từ pipeline dùng JDK khác.
- Một dependency bọc API preview và chỉ tải class đó khi chạy một nhánh code hiếm.

Vì class loading có thể diễn ra lazy, việc ứng dụng khởi động thành công không chứng minh toàn bộ dependency graph không chứa class preview. Hãy kiểm tra artifact và chạy integration test bao phủ các luồng sẽ tải những class đó.

### Không nhầm preview class file với incubator module

Preview feature và incubator module đều có thể thay đổi, nhưng cơ chế phát hành khác nhau:

| Tiêu chí | Preview feature/API | Incubator module/API |
|---|---|---|
| Mục tiêu | Thử nghiệm một tính năng của release Java SE cụ thể trước khi final hoặc bị rút. | Thử nghiệm một module/API có thể được tinh chỉnh trước khi trở thành chuẩn hoặc bị loại. |
| Cờ sử dụng phổ biến | `--enable-preview` khi compile và run. | `--add-modules jdk.incubator...` khi compile/run nếu module cần được resolve. |
| Class file marker | Class file phụ thuộc preview có minor version `65535`, gắn với release. | Không tự động mang minor version `65535` chỉ vì dùng incubator API; class file có thể là version thông thường. |
| Rủi ro nâng cấp | JVM khác release từ chối class file preview. | Module/API có thể đổi, đổi tên hoặc bị loại; cần dependency/module compatibility và compile/test lại. |

Ví dụ `jdk.incubator.vector` là incubator module. Việc sử dụng Vector API cần module tương ứng được resolve, nhưng không được suy luận rằng mọi class dùng Vector API đều có preview marker. Nếu cùng source còn dùng preview language feature, class file có thể phụ thuộc preview vì lý do đó. Không dùng quy tắc minor version `65535` để thay thế kiểm tra module/API của incubator.

## 7. Phân biệt ba trường hợp khi nâng cấp JDK

| Artifact hiện có | Chuyển sang JDK mới | Hướng xử lý |
|---|---|---|
| Class file thường, major version thấp hơn hoặc bằng runtime và minor `0` | Thường có thể được JVM mới tải. | Kiểm tra API, dependency và hành vi; test trên runtime đích. |
| Class file thường có major version cao hơn runtime | Runtime cũ không hiểu định dạng mới. | Biên dịch lại với `--release` phù hợp hoặc nâng runtime. |
| Class file preview, minor `65535` của release khác runtime | JVM từ chối ngay cả khi bật `--enable-preview`. | Lấy source và biên dịch lại bằng đúng release đích; hoặc thay dependency bằng bản stable. |
| Class file preview cùng release với runtime nhưng preview tắt | JVM từ chối tải class. | Chỉ trong môi trường thử nghiệm, bật `--enable-preview` đúng release; nếu production cần ổn định, loại bỏ preview. |

Đối với Java 26, class file thường `70.0` có thể được JDK 27 hỗ trợ về định dạng. Class file preview `70.65535` chỉ dành cho Java 26. Java 27 có major version `71`; class file preview của Java 27 là `71.65535` và cũng chỉ chạy với runtime Java 27 có preview bật. Không suy luận rằng major version gần nhau đồng nghĩa preview binary tương thích.

## 8. Kiểm tra class file bằng `javap`

`javap -verbose` hiển thị major/minor version của class file. Ví dụ:

```bash
javap -verbose -classpath app-preview-26.jar com.example.Main
```

Tìm hai dòng:

```text
minor version: 65535
major version: 70
```

Kết quả trên cho biết class file phụ thuộc preview của Java 26. Một class file ổn định Java 26 thông thường có dạng:

```text
minor version: 0
major version: 70
```

Có thể kiểm tra một class trong dependency JAR bằng cách đặt JAR đó trên classpath:

```bash
javap -verbose -classpath vendor-library.jar com.vendor.Parser
```

`javap` kiểm tra class cụ thể. Để audit dependency graph, cần duyệt các class entry trong toàn bộ JAR/module được triển khai và kiểm tra version của từng class; không chỉ kiểm tra class main. `jar tf` chỉ liệt kê entry, không hiển thị class file version. `jdeps` hữu ích để xem phụ thuộc module/package, nhưng không thay thế việc kiểm tra minor version `65535`.

### Kiểm tra byte header khi cần điều tra sâu

Class file bắt đầu bằng magic `CAFEBABE`, tiếp theo là minor version và major version, mỗi trường 2 byte theo thứ tự big-endian. Với Java 26 preview, phần version là:

```text
CA FE BA BE  FF FF  00 46  ...
             ^^^^^  ^^^^^
             minor  major 70
```

Trong vận hành thông thường, dùng `javap -verbose` thay vì tự phân tích byte. Ví dụ hex chỉ giúp hiểu rằng `65535` được lưu ở dạng unsigned 16-bit `0xFFFF`.

## 9. Rebuild dependency graph khi đổi JDK

Khi nâng cấp từ Java 26 sang Java 27, không chỉ đổi `JAVA_HOME` rồi giữ nguyên toàn bộ output directory. Thực hiện theo thứ tự:

1. Chốt JDK đích và release target: Java 27 stable, Java 27 preview, hoặc một baseline thấp hơn.
2. Kiểm tra source có dùng preview API/language feature hay không.
3. Kiểm tra dependency JAR, plugin, annotation processor và generated class file có minor version `65535` hay không.
4. Cập nhật dependency sang phiên bản hỗ trợ JDK đích; ưu tiên bản không phụ thuộc preview.
5. Tạo output directory/build cache mới cho JDK đích để tránh class file cũ còn sót.
6. Biên dịch lại toàn bộ module liên quan từ source bằng compiler đích.
7. Kiểm tra class file version và dependency graph sau build.
8. Chạy unit, integration, packaging và startup tests trên đúng runtime image sẽ triển khai.
9. Kiểm tra command line production không vô tình bật `--enable-preview` nếu artifact được kỳ vọng stable.

Không copy `.class` hoặc JAR từ output preview release trước vào output của release mới. Không đổi hai byte version trong class file bằng hex editor để làm cho JVM chấp nhận; việc sửa header không chuyển đổi bytecode, constant pool, semantics hay API preview sang release mới.

### Cache và artifact repository

Build cache có thể trả về output đã biên dịch bằng JDK khác nếu cache key không bao gồm compiler version, release target và preview flag. Đảm bảo build pipeline phân biệt ít nhất:

- JDK vendor và version đầy đủ (bao gồm update/build nếu policy yêu cầu).
- `--release` hoặc source/target baseline.
- Trạng thái `--enable-preview`.
- Các compiler plugin và annotation processor version.
- Dependency lock/version và toolchain configuration.

Đặt tên artifact rõ ràng, ví dụ `app-java26-preview` cho artifact chỉ dùng trong thử nghiệm Java 26. Không publish nó dưới tên artifact stable chung khiến pipeline khác tải về mà không biết yêu cầu runtime.

## 10. Kiểm thử ma trận compiler/runtime

Nếu tổ chức đang chuyển nhiều dịch vụ giữa JDK, tạo ma trận test thể hiện đúng cam kết hỗ trợ:

| Compiler | Runtime | Artifact | Kỳ vọng |
|---|---|---|---|
| JDK 26, không preview | JDK 26 | `70.0` | Có thể chạy nếu dependency/API tương thích. |
| JDK 26, preview | JDK 26 + `--enable-preview` | `70.65535` | Có thể chạy theo preview Java 26. |
| JDK 26, preview | JDK 27 + `--enable-preview` | `70.65535` | Bị từ chối vì class file preview của release khác. |
| JDK 27, preview | JDK 27 + `--enable-preview` | `71.65535` | Có thể chạy theo preview Java 27. |
| JDK 26, không preview, `--release 25` | JDK 25 | Class file baseline Java 25 | Có thể chạy nếu source/API thực sự tương thích Java 25. |

Đừng chỉ test trên JDK mới nhất. Runtime production phải được test bằng đúng phiên bản, flags, module path, dependency set và container image sẽ chạy. Với preview, kiểm thử cả trường hợp thiếu `--enable-preview` để phát hiện cấu hình launch sai; với nâng cấp, test class loading của các plugin và đường code lazy-load.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Preview features are not enabled for ...` | Class file preview cùng release nhưng runtime chưa bật preview. | Chỉ trong môi trường thử nghiệm, thêm `--enable-preview` cho đúng JDK; hoặc rebuild không dùng preview. |
| `UnsupportedClassVersionError` với preview class từ JDK cũ | Minor version `65535` gắn với release khác. | Recompile từ source bằng JDK đích; thay dependency nếu không có source. |
| Chạy được trên máy dev nhưng fail trên container | Dev và container dùng JDK khác hoặc thiếu runtime flag. | Kiểm tra `java -version`, image digest, command line và class file version. |
| App khởi động được nhưng lỗi khi gọi plugin | Plugin class được tải lazy và chứa preview marker không tương thích. | Audit toàn bộ plugin/dependency và test các nhánh kích hoạt chúng. |
| Rebuild vẫn gặp lỗi class preview cũ | Build cache hoặc output directory giữ `.class` cũ. | Dùng output/cache key mới theo JDK và preview flag; rebuild dependency graph. |
| `javap` hiển thị `70.0` nhưng ứng dụng vẫn lỗi | Class khác trong dependency có thể là preview hoặc dùng API không có ở runtime. | Kiểm tra class thực sự được nạp và dependency graph, không chỉ main class. |
| JAR có `META-INF/versions/` nhưng runtime vẫn lỗi | Multi-release JAR chọn class theo runtime; class được chọn vẫn có thể là preview marker không hợp lệ. | Audit từng class entry theo version directory và runtime selection. |

Không sửa lỗi bằng cách bỏ kiểm tra version, đổi header class file, thêm một cờ preview vào runtime release khác hoặc tắt verifier. Các thao tác đó không tạo ra binary tương thích và có thể che giấu lỗi cho tới khi class được tải trong production.

## 12. Khuyến nghị cho triển khai ổn định

Với hệ thống cần nâng cấp JDK định kỳ, nên xem preview là một nhánh thử nghiệm có giới hạn:

- Giữ preview code trong module hoặc service tách biệt, tránh để class preview lan vào thư viện dùng chung.
- Không phát hành class file preview vào artifact stable hoặc public library.
- Ghi rõ JDK release và `--enable-preview` trong metadata của artifact thử nghiệm.
- Cố định compiler/runtime cùng release cho test và deployment.
- Theo dõi JEP của feature để biết thay đổi, re-preview, finalization hoặc withdrawal.
- Khi feature final, sửa source theo API/ngữ nghĩa chính thức rồi rebuild bình thường; không tái sử dụng class file preview cũ.
- Khi feature bị rút, thay bằng API ổn định hoặc thiết kế khác trước khi nâng cấp runtime.
- Với dependency bên thứ ba, yêu cầu vendor công bố JDK baseline và việc có sử dụng preview/incubator hay không.

Nếu yêu cầu tương thích nhiều JDK là ưu tiên, compile bằng `--release` thấp nhất mà sản phẩm cam kết hỗ trợ và không dùng preview. Với code cần dùng preview để đánh giá tính năng, chấp nhận rõ ràng rằng artifact chỉ phục vụ đúng JDK release đó.

## 13. Checklist trước khi nâng cấp JDK

- [ ] Đã xác định runtime đích và class file baseline cần hỗ trợ.
- [ ] Đã phân biệt class file thường `minor=0` với preview class file `minor=65535`.
- [ ] Đã biết Java 26 dùng major version `70`; Java 26 preview là `70.65535`.
- [ ] Đã xác nhận class file preview chỉ được tải bởi đúng release và khi preview được bật.
- [ ] Đã kiểm tra preview class trong tất cả dependency, plugin, processor và generated output.
- [ ] Đã phân biệt preview feature với incubator module; không dùng `--enable-preview` như cách bật incubator module.
- [ ] Đã biên dịch preview bằng compiler đúng release và chạy bằng runtime cùng release.
- [ ] Đã dùng `--release` phù hợp; không kỳ vọng `--release` cũ giữ được preview của release mới.
- [ ] Đã dùng output directory/cache key riêng theo JDK, release target và preview flag.
- [ ] Đã kiểm tra class version bằng `javap -verbose` và audit dependency JAR.
- [ ] Đã chạy integration test trên đúng runtime image và command line triển khai.
- [ ] Artifact stable không chứa class file preview và không yêu cầu `--enable-preview`.
- [ ] Đã có kế hoạch rebuild hoặc thay thế dependency khi preview thay đổi hay bị rút.

## Tài liệu tham khảo chính thức

- [JEP 12 — Preview Features](https://openjdk.org/jeps/12)
- [Java SE 26 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html)
- [Java SE 26 — Primitive Types in Patterns, `instanceof`, and `switch` (JEP 530)](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html)
- [Java SE 26 — Java Virtual Machine Specification, Chapter 1](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-1.html)
- [Java SE 26 — Java Virtual Machine Specification, Chapter 4](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html)
- [Java SE 26 — `ClassFileVersion`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/ClassFileVersion.html)
- [JDK 26 — `javac` Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [JDK 26 — `java` Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Java SE 27 — Java Virtual Machine Specification, Chapter 4](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html)

*Cập nhật nội dung: 27-11-2026. Class file preview có minor version `65535` và chỉ chạy trên đúng release khi bật preview. Không sửa header để vượt qua kiểm tra; hãy rebuild từ source hoặc thay dependency bằng bản stable.*
