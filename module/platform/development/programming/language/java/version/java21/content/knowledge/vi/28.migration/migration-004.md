# Phân tích dependency bằng jdeps và API có cảnh báo bằng jdeprscan

Khi nâng ứng dụng lên Java 21, cần biết bytecode đang phụ thuộc vào những package, module và API nào của JDK. Hai công cụ có vai trò bổ sung cho nhau:

- `jdeps` phân tích dependency ở mức package/class/module và có thể tìm tham chiếu tĩnh tới JDK internal APIs.
- `jdeprscan` quét class file hoặc JAR để tìm cách sử dụng các Java SE API đã được đánh dấu deprecated, gồm cả API deprecated for removal.

Cả hai đều là công cụ phân tích tĩnh trên bytecode. Chúng giúp phát hiện rủi ro trước khi chạy ứng dụng, nhưng không thay thế việc nâng cấp thư viện, biên dịch lại, chạy test và kiểm thử trên đúng JDK 21.

## 1. Chuẩn bị artifact cần phân tích

Hai công cụ làm việc với file `.class`, thư mục chứa class hoặc JAR đã biên dịch. Vì vậy, trước khi chạy:

1. Build ứng dụng và các module bằng cấu hình dành cho Java 21.
2. Xác định JAR hoặc thư mục class thực sự được deploy.
3. Thu thập dependency runtime mà ứng dụng sử dụng.
4. Ghi lại phiên bản JDK, dependency và cấu hình build để có thể so sánh kết quả giữa các lần chạy.

Ví dụ cấu trúc artifact:

~~~text
build/
  classes/
  libs/
    application.jar
    library-a.jar
    library-b.jar
~~~

Nếu ứng dụng chạy bằng classpath, cung cấp các thư viện cần thiết qua `--class-path`. Nếu ứng dụng dùng Java Platform Module System, cung cấp module qua `--module-path` và chỉ định module cần phân tích khi phù hợp.

Không nên phân tích một JAR cũ trong khi production đang chạy một bản khác. Kết quả chỉ có ý nghĩa khi artifact đầu vào phản ánh đúng thứ sẽ được triển khai.

## 2. jdeps cho biết dependency nào?

`jdeps` đọc dependency được thể hiện trong class file và có thể trình bày ở nhiều mức:

- **Package-level:** package nào phụ thuộc package nào.
- **Class-level:** class nào tham chiếu class nào.
- **Module-level:** module JDK hoặc module ứng dụng nào cần thiết.
- **API-level:** dependency xuất hiện trong chữ ký public/protected của API công khai.
- **JDK internal APIs:** dependency tĩnh tới package hoặc class nội bộ của JDK.

Một báo cáo tổng quan giúp nhìn thấy ứng dụng cần những module JDK nào:

~~~bash
jdeps -summary build/libs/application.jar
~~~

Để xem dependency chi tiết ở mức class:

~~~bash
jdeps -verbose:class build/libs/application.jar
~~~

Nếu muốn duyệt dependency đệ quy qua các thư viện runtime:

~~~bash
jdeps --recursive --class-path "build/libs/library-a.jar;build/libs/library-b.jar" build/libs/application.jar
~~~

Ví dụ classpath trên dùng dấu chấm phẩy theo quy ước Windows. Trên Linux/macOS, thay dấu phân cách bằng dấu hai chấm. Thay các đường dẫn mẫu bằng đúng runtime classpath của ứng dụng.

`--recursive` yêu cầu phân tích tiếp các dependency có thể tìm thấy. Nếu thiếu thư viện, bổ sung đúng classpath hoặc module path trước khi kết luận. Không nên bỏ qua thông báo dependency không tìm thấy vì đồ thị khi đó chưa đầy đủ.

## 3. Tìm JDK internal API bằng jdeps

Một rủi ro quan trọng khi nâng cấp JDK là ứng dụng hoặc thư viện phụ thuộc vào API nội bộ, thường xuất hiện trong các package như `sun.*` hoặc một số package có tiền tố `com.sun.*`. Không kết luận chỉ dựa vào tên package: một số package `com.sun.*` được export như API JDK công khai. Hãy dựa vào kết quả `jdeps` và tài liệu API của JDK để xác định package có được hỗ trợ hay không.

Dùng `--jdk-internals` để tìm dependency tĩnh tới JDK internal APIs:

~~~bash
jdeps --jdk-internals build/libs/application.jar
~~~

Để mở rộng phân tích qua dependency và chỉ rõ runtime classpath:

~~~bash
jdeps --jdk-internals --recursive --class-path "build/libs/library-a.jar;build/libs/library-b.jar" build/libs/application.jar
~~~

Nếu đầu vào là multi-release JAR, chỉ định phiên bản cần phân tích:

~~~bash
jdeps --multi-release 21 --jdk-internals --recursive build/libs/application.jar
~~~

`--multi-release 21` yêu cầu `jdeps` chọn phần class phù hợp với Java 21 trong multi-release JAR. Với JAR thông thường, có thể bỏ tùy chọn này.

Kết quả giúp xác định class nào tham chiếu internal API và API nào cần được thay thế hoặc cô lập. Ví dụ, nếu thư viện sử dụng một class nội bộ để xử lý buffer hoặc reflection, hãy kiểm tra phiên bản thư viện mới hơn và API công khai mà thư viện đó nên dùng.

### Vì sao dependency tới internal API là rủi ro?

Internal API không có cam kết tương thích như Java SE API công khai. Chúng có thể bị đóng gói, thay đổi hoặc loại bỏ giữa các phiên bản JDK.

Từ Java 17, JDK áp dụng strong encapsulation mặc định cho phần lớn internal elements. Khi code cố truy cập reflective vào field hoặc method không được mở của các package `java.*`, ứng dụng có thể nhận `InaccessibleObjectException`.

Một số internal API quan trọng vẫn tồn tại vì lý do tương thích, nhưng việc chúng còn có mặt không biến chúng thành API được hỗ trợ cho ứng dụng. Nên ưu tiên thay thế bằng API Java SE hoặc cập nhật thư viện phụ thuộc.

## 4. Phân biệt dependency API công khai và dependency nội bộ

Không phải mọi dependency được `jdeps` liệt kê đều là vấn đề. Ví dụ, phụ thuộc vào `java.base`, `java.sql` hoặc `java.net.http` có thể hoàn toàn hợp lệ.

Cần phân loại kết quả:

| Kết quả | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Dependency tới Java SE API công khai | Ứng dụng dùng API được hỗ trợ | Kiểm tra API có bị deprecated hoặc thay đổi hành vi không |
| Dependency tới JDK internal API | Ứng dụng dựa vào chi tiết triển khai của JDK | Tìm API thay thế hoặc nâng cấp thư viện |
| Dependency tới module JDK không có trong runtime image | Runtime tùy chỉnh có thể thiếu module | Kiểm tra cấu hình module và image |
| Dependency không tìm thấy | Classpath/module path chưa đầy đủ hoặc artifact thiếu dependency | Bổ sung dependency rồi chạy lại |
| Dependency trong public/protected signature | API công khai của thư viện làm lộ kiểu phụ thuộc | Kiểm tra ảnh hưởng tới consumer và khả năng đóng gói |

Nếu muốn chỉ phân tích dependency xuất hiện trong chữ ký API public/protected:

~~~bash
jdeps --api-only --verbose:class build/libs/application.jar
~~~

Tùy chọn `--api-only` hữu ích khi kiểm tra một thư viện được nhiều ứng dụng khác sử dụng. Một dependency nội bộ có thể được thay đổi dễ hơn dependency xuất hiện trong public API vì consumer bên ngoài có thể đang phụ thuộc vào kiểu đó.

## 5. Phân tích module và dependency của runtime image

Nếu ứng dụng dùng module path, `jdeps` có thể giúp xác định module cần thiết và kiểm tra module descriptor.

Liệt kê module dependency:

~~~bash
jdeps --list-deps --recursive build/libs/application.jar
~~~

In danh sách module dependency rút gọn:

~~~bash
jdeps --print-module-deps --recursive build/libs/application.jar
~~~

Danh sách do `--print-module-deps` tạo ra có thể dùng làm đầu vào cho `jlink --add-modules` khi tạo runtime image tùy chỉnh. Trước khi tạo image, hãy xác minh rằng phân tích đã bao gồm các dependency runtime cần thiết và không có classpath dependency bị thiếu.

Nếu đang phân tích một ứng dụng module hóa, có thể kiểm tra module cụ thể trên module path:

~~~bash
jdeps --module-path build/mods --check com.example.application
~~~

`--check` hiển thị module descriptor, dependency sau phân tích và đồ thị module sau khi loại bỏ các cạnh được suy ra. Kết quả cũng có thể chỉ ra qualified export không còn được sử dụng.

Các tùy chọn module không thay thế việc kiểm thử runtime image thực tế. Service loading, reflection, resource lookup và cấu hình chạy có thể tạo ra yêu cầu mà phân tích bytecode tĩnh không mô tả đầy đủ.

## 6. Tìm dependency bị thiếu và xuất đồ thị

Khi dependency graph có vẻ chưa đầy đủ, chạy kiểm tra dependency bị thiếu:

~~~bash
jdeps --missing-deps --class-path "build/libs/library-a.jar;build/libs/library-b.jar" build/libs/application.jar
~~~

Nếu cần trực quan hóa dependency giữa các archive, xuất đồ thị DOT:

~~~bash
jdeps --dot-output build/reports/jdeps build/libs/application.jar
~~~

Thư mục output chứa file `.dot` cho archive và một file tổng hợp. Có thể mở chúng bằng công cụ hỗ trợ Graphviz để nhìn thấy quan hệ giữa các JAR.

Đừng dùng `--ignore-missing-deps` như cách che lỗi phân tích trong báo cáo migration. Chỉ bỏ qua dependency thiếu khi đã hiểu rõ nguyên nhân và có một phạm vi kiểm tra riêng.

## 7. jdeprscan tìm API deprecated như thế nào?

`jdeprscan` quét class file, thư mục class hoặc JAR để phát hiện việc sử dụng các API Java SE được đánh dấu deprecated.

Công cụ hữu ích trong các trường hợp:

- Ứng dụng chưa được biên dịch lại trên từng phiên bản JDK.
- Warning deprecation khi compile đã bị tắt hoặc bị suppress.
- Ứng dụng sử dụng thư viện binary mà source code không nằm trong repository.
- Muốn rà soát API deprecated for removal trước khi nâng cấp JDK.

Quét một JAR theo bộ API của Java 21:

~~~bash
jdeprscan --release 21 build/libs/application.jar
~~~

Chỉ tập trung vào API đã được đánh dấu deprecated for removal:

~~~bash
jdeprscan --release 21 --for-removal build/libs/application.jar
~~~

Liệt kê các API deprecated for removal của Java 21:

~~~bash
jdeprscan --release 21 --list --for-removal
~~~

Khi dùng `--list`, không truyền JAR, thư mục hoặc tên class vì lệnh chỉ in danh sách API, không quét artifact.

`--release 21` chọn bộ API deprecation của Java SE 21 để đối chiếu. Đây là lựa chọn rõ ràng cho một đợt migration hướng tới Java 21, đặc biệt khi công cụ được chạy từ một JDK khác có hỗ trợ release đó.

## 8. Cung cấp classpath cho jdeprscan

Để phân tích class file chính xác, `jdeprscan` cần phân giải được các class mà artifact phụ thuộc. Nếu thiếu class, công cụ có thể báo dạng:

~~~text
error: cannot find class ...
~~~

Khi gặp lỗi này, bổ sung các dependency vào `--class-path`:

~~~bash
jdeprscan --release 21 --class-path "build/classes;build/libs/library-a.jar;build/libs/library-b.jar" build/libs/application.jar
~~~

Trên Windows, classpath dùng dấu chấm phẩy (`;`). Trên Linux/macOS, dùng dấu hai chấm (`:`).

Có thể quét cả thư mục class đã biên dịch:

~~~bash
jdeprscan --release 21 build/classes
~~~

Hoặc quét một class cụ thể bằng tên đầy đủ:

~~~bash
jdeprscan --release 21 com.example.application.LegacyAdapter
~~~

Nếu scan một class riêng lẻ và class đó phụ thuộc thư viện ngoài, vẫn cần truyền `--class-path` tương ứng. Một lần chạy không có warning chỉ đáng tin khi quá trình phân giải dependency không có lỗi.

## 9. Hiểu kết quả deprecated và deprecated for removal

Java có hai trạng thái cần phân biệt:

- **Deprecated:** API không còn được khuyến nghị sử dụng; tài liệu API thường mô tả lý do và hướng thay thế.
- **Deprecated for removal:** API đã được đánh dấu rõ rằng có ý định loại bỏ trong một phiên bản JDK tương lai. Đây là rủi ro migration cần ưu tiên cao hơn.

Annotation `@Deprecated` lưu thông tin trong class file. Thuộc tính `since` cho biết phiên bản bắt đầu deprecated; `forRemoval = true` thể hiện ý định loại bỏ.

Một API deprecated chưa chắc bị xóa ngay trong Java 21. Ngược lại, nếu API đã bị loại bỏ trước Java 21 thì không thể chỉ dựa vào danh sách deprecated hiện tại để tìm mọi cách sử dụng cũ. Hãy kiểm tra mục Removed APIs trong Java 21 Migration Guide và thử compile/chạy trên JDK 21.

Có thể ưu tiên xử lý theo bảng sau:

| Mức ưu tiên | Kết quả | Hành động |
|---|---|---|
| Rất cao | API đã bị loại bỏ hoặc dependency internal gây lỗi trên Java 21 | Thay thế hoặc nâng cấp dependency trước khi phát hành |
| Cao | API deprecated for removal trong Java 21 | Lập kế hoạch thay thế và kiểm thử ngay |
| Trung bình | API deprecated nhưng chưa for removal | Đánh giá API thay thế và đưa vào backlog migration |
| Cần điều tra | Thiếu dependency hoặc không phân giải được class | Hoàn thiện classpath rồi quét lại |

Không nên tự động thay mọi API deprecated chỉ dựa vào tên. Hãy đọc Javadoc của API để hiểu lý do deprecation, thay đổi ngữ nghĩa và API thay thế được đề xuất.

## 10. jdeprscan không kiểm tra deprecation của thư viện bên thứ ba

`jdeprscan` chỉ nhận diện deprecated API được định nghĩa bởi Java SE. Nó không báo các method hoặc class do thư viện bên thứ ba đánh dấu `@Deprecated`.

Để kiểm tra dependency ngoài JDK, kết hợp các nguồn sau:

- Release notes và migration guide của từng thư viện.
- Dependency report của Maven hoặc Gradle.
- Compiler warnings khi biên dịch source.
- Công cụ phân tích dependency/security của hệ sinh thái đang dùng.
- Integration test chạy với đúng phiên bản dependency dự kiến triển khai.

Ví dụ, nếu một thư viện HTTP client hoặc ORM đánh dấu method deprecated, `jdeprscan` có thể không báo vì API đó không thuộc Java SE. Cần nâng cấp hoặc thay thế dựa trên tài liệu của chính thư viện đó.

## 11. Giới hạn của phân tích tĩnh

`jdeps` và `jdeprscan` đọc thông tin có trong bytecode. Chúng không thể xác minh mọi đường đi mà ứng dụng có thể thực hiện ở runtime.

Một số trường hợp có thể không được phát hiện đầy đủ:

- Reflection sử dụng tên class, field hoặc method được tạo từ chuỗi runtime.
- `Class.forName`, method handle hoặc service loading phụ thuộc cấu hình động.
- JNI/native code truy cập thành phần ngoài bytecode Java.
- Class được tải từ plugin, script engine hoặc vị trí không có trong artifact đã scan.
- Dependency được thêm vào runtime qua container, application server hoặc module layer riêng.

Vì vậy, kết quả `jdeps` sạch không chứng minh ứng dụng không sử dụng internal API qua reflection. Cần chạy test trên Java 21, kiểm tra log lỗi truy cập module và thử các luồng chức năng có dùng framework/plugin.

## 12. Strong encapsulation và cách xử lý quyền truy cập

Java 21 áp dụng strong encapsulation cho phần lớn internal elements của JDK. Một số thư viện cũ có thể cố truy cập field hoặc method không public qua reflection và gặp `InaccessibleObjectException`.

Quy trình xử lý nên theo thứ tự:

1. Xác định class và package gây lỗi từ stack trace.
2. Kiểm tra phiên bản thư viện và nâng cấp lên bản hỗ trợ Java 21.
3. Nếu là code của ứng dụng, thay internal API bằng Java SE API công khai.
4. Nếu chưa thể loại bỏ ngay, chỉ cấp quyền mở/export cho đúng module, package và module đích trong thời gian chuyển tiếp.
5. Ghi nhận lý do và kế hoạch loại bỏ từng quyền truy cập tạm thời.

Hai tùy chọn module có mục đích khác nhau:

- `--add-exports` cho phép truy cập các public type/member của package chưa được module export.
- `--add-opens` mở package cho deep reflection khi cần truy cập member không public.

Không dùng `--illegal-access=permit`, `warn` hoặc `deny` làm giải pháp migration. Tùy chọn `--illegal-access` đã obsolete từ Java 17 và bị bỏ qua trên Java 21; nó không khôi phục cơ chế relaxed encapsulation cũ.

Một cờ `--add-opens` hoặc `--add-exports` có thể giúp một thư viện cũ tiếp tục chạy trong thời gian ngắn, nhưng không biến internal API thành API ổn định. Cần theo dõi và loại bỏ các cờ này khi dependency đã được cập nhật.

## 13. Kết hợp jdeps và jdeprscan trong một quy trình migration

Hai công cụ trả lời hai câu hỏi khác nhau:

| Câu hỏi | Công cụ | Lệnh gợi ý |
|---|---|---|
| Ứng dụng phụ thuộc package/class/module nào? | `jdeps` | `jdeps -summary application.jar` |
| Có tham chiếu tĩnh tới JDK internal API không? | `jdeps` | `jdeps --jdk-internals application.jar` |
| Module JDK nào cần cho runtime? | `jdeps` | `jdeps --print-module-deps application.jar` |
| Có Java SE API deprecated không? | `jdeprscan` | `jdeprscan --release 21 application.jar` |
| Có API deprecated for removal không? | `jdeprscan` | `jdeprscan --release 21 --for-removal application.jar` |
| API nào trong Java 21 đã được đánh dấu for removal? | `jdeprscan` | `jdeprscan --release 21 --list --for-removal` |

Một quy trình thực tế:

1. Build artifact và lưu runtime classpath.
2. Chạy `jdeps -summary` để hiểu dependency tổng thể.
3. Chạy `jdeps --jdk-internals --recursive` để tìm internal API trong ứng dụng và dependency có thể phân tích.
4. Sửa hoặc nâng cấp thư viện có internal API; chạy lại `jdeps` để xác minh.
5. Chạy `jdeprscan --release 21` và `--for-removal` để phân loại API deprecated.
6. Đối chiếu Removed APIs trong Java 21 Migration Guide.
7. Cập nhật source và dependency, rồi biên dịch lại.
8. Chạy test/integration test trên JDK 21 và kiểm tra các đường đi reflection, plugin hoặc native.
9. Lưu kết quả scan vào pipeline CI để phát hiện dependency rủi ro mới trong các lần build tiếp theo.

Nếu cần tiếp tục hỗ trợ một thư viện chưa thể nâng cấp, hãy ghi rõ package, module, phiên bản thư viện, lý do cần truy cập và cờ module tạm thời. Không chấp nhận một báo cáo migration chỉ ghi "đã thêm add-opens" mà không có nguyên nhân và kế hoạch loại bỏ.

## 14. Tự động hóa trong CI

Có thể đưa hai công cụ vào pipeline sau bước build artifact. Ví dụ lệnh scan trong script CI:

~~~bash
jdeps --jdk-internals --recursive --class-path "$RUNTIME_CLASSPATH" build/libs/application.jar
jdeprscan --release 21 --class-path "$RUNTIME_CLASSPATH" build/libs/application.jar
jdeprscan --release 21 --for-removal --class-path "$RUNTIME_CLASSPATH" build/libs/application.jar
~~~

Thiết kế pipeline theo hướng:

- Lưu output để so sánh giữa các lần build.
- Cảnh báo khi xuất hiện dependency internal mới.
- Đặt mức ưu tiên cao cho API deprecated for removal.
- Không coi cảnh báo thiếu classpath là kết quả scan thành công.
- Giữ allowlist có lý do và người chịu trách nhiệm nếu một dependency chưa thể thay thế.
- Chạy lại sau khi nâng cấp dependency vì dependency bắc cầu có thể thay đổi.

Có thể bổ sung compile warning bằng:

~~~bash
javac -Xlint:deprecation,removal ...
~~~

Compiler warnings hữu ích cho source đang được biên dịch. `jdeprscan` bổ sung góc nhìn trên bytecode đã có sẵn, bao gồm JAR binary không có source trong repository.

## 15. Checklist trước khi hoàn tất migration lên Java 21

- [ ] Artifact đầu vào đúng với bản build sẽ triển khai.
- [ ] Classpath/module path có đủ dependency runtime.
- [ ] Đã chạy `jdeps -summary` và xem dependency tổng quan.
- [ ] Đã chạy `jdeps --jdk-internals` trên ứng dụng và các JAR cần kiểm tra.
- [ ] Đã kiểm tra dependency đệ quy và multi-release JAR nếu có.
- [ ] Đã xử lý hoặc ghi nhận mọi dependency tới JDK internal API.
- [ ] Đã chạy `jdeprscan --release 21`.
- [ ] Đã chạy thêm `jdeprscan --release 21 --for-removal`.
- [ ] Đã đối chiếu API đã bị loại bỏ trong Java 21 Migration Guide.
- [ ] Đã kiểm tra dependency bên thứ ba bằng release notes/compiler warnings.
- [ ] Đã rà soát các đường truy cập reflection, plugin, JNI và native.
- [ ] Không dựa vào `--illegal-access` để khôi phục hành vi cũ.
- [ ] Mọi `--add-exports` hoặc `--add-opens` còn lại đều có phạm vi, lý do và kế hoạch loại bỏ.
- [ ] Test và integration test chạy trên JDK 21 thành công.
- [ ] Kết quả scan được lưu trong CI để theo dõi các lần build tiếp theo.

## Tài liệu tham khảo chính thức

- [Java SE 21 Tool Specifications — jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html)
- [Java SE 21 Tool Specifications — jdeprscan](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html)
- [Oracle Java 21 — Running jdeprscan](https://docs.oracle.com/en/java/javase/21/core/running-jdeprscan.html)
- [Oracle Java 21 Migration Guide — Removed APIs](https://docs.oracle.com/en/java/javase/21/migrate/removed-apis.html)
- [Oracle Java 21 Migration Guide — Migrating from JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/21/migrate/migrating-jdk-8-later-jdk-releases.html)
- [Oracle Java 21 — Enhanced Deprecation](https://docs.oracle.com/en/java/javase/21/core/enhanced-deprecation1.html)
- [Oracle Java 21 — How to Deprecate APIs](https://docs.oracle.com/en/java/javase/21/core/how-deprecate-apis.html)
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)

