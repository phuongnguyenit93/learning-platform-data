# Phân biệt chạy mã hiện có trên JDK 21 với biên dịch bằng `--release 21`

## Mục tiêu

Khi nâng cấp ứng dụng lên Java 21, có hai việc thường bị nhầm lẫn:

- **Chạy mã đã biên dịch trên JDK 21:** lấy file `.class` hoặc JAR hiện có và chạy bằng JVM của JDK 21 để kiểm tra khả năng tương thích runtime.
- **Biên dịch mã nguồn bằng `--release 21`:** dùng compiler để tạo bytecode Java 21 và cho phép mã nguồn truy cập API Java SE thuộc phiên bản 21.

Hai việc này trả lời hai câu hỏi khác nhau. Một ứng dụng được biên dịch từ Java 8 hoặc Java 17 có thể chạy trên JDK 21 mà không cần biên dịch lại, nhưng điều đó không chứng minh mã nguồn có thể biên dịch với Java 21. Ngược lại, biên dịch thành công bằng `--release 21` không chứng minh ứng dụng và toàn bộ dependency sẽ chạy ổn định trong môi trường production.

Bài học này giải thích class-file version, phạm vi của `--release`, cách kiểm tra runtime compatibility và cách chọn target Java cho artifact phát hành.

## 1. Tách biệt runtime JDK và compile target

Một ứng dụng Java có thể liên quan đến nhiều phiên bản Java:

| Thành phần | Vai trò |
|---|---|
| JDK dùng để build | Cung cấp compiler, tool và thư viện phục vụ build |
| `--release` | Xác định phiên bản Java mà source/API/bytecode được biên dịch hướng tới |
| JVM dùng để chạy | Runtime thực thi bytecode và cung cấp các API ở môi trường triển khai |
| Dependency | Các JAR hoặc module bên ngoài mà ứng dụng cần khi build hoặc chạy |

Ví dụ, có thể dùng JDK 21 để biên dịch mã nguồn hướng tới Java 17 bằng `javac --release 17`, sau đó chạy artifact trên Java 17. Cũng có thể dùng JDK 21 để biên dịch bằng `--release 21` và chạy artifact trên Java 21.

Điểm cần nhớ: **phiên bản JDK thực hiện build không tự quyết định phiên bản Java tối thiểu mà artifact hỗ trợ**. Compile target và API contract được xác định bởi `--release` (hoặc các tùy chọn tương ứng trong build tool).

## 2. Chạy bytecode cũ trên JDK 21 là kiểm tra runtime compatibility

JVM mới thường hỗ trợ chạy class file được tạo cho các phiên bản Java cũ hơn. Vì vậy, ứng dụng đã biên dịch bằng JDK cũ có thể được chạy trực tiếp trên JDK 21 mà không cần biên dịch lại.

Ví dụ, một JAR được biên dịch với target Java 17 có thể được thử chạy bằng JVM Java 21:

```bash
java -version
java -jar application.jar
```

Lệnh `java -version` xác nhận runtime đang được gọi. Lệnh `java -jar` kiểm tra ứng dụng đã đóng gói có khởi động và thực thi trên runtime đó hay không.

Nếu ứng dụng dùng classpath thay vì executable JAR:

```bash
java -cp "app/classes;app/lib/*" com.example.Main
```

Trên Linux/macOS, dấu phân cách classpath thường là `:`; ví dụ trên dùng dấu `;` của Windows. Hãy chạy bằng đúng lệnh và cấu hình triển khai thực tế, bao gồm JVM flags, environment variables, module path và dependency.

Chạy thành công một lần chỉ chứng minh luồng đã thực thi trong điều kiện đó. Cần chạy test tích hợp, test nghiệp vụ và kiểm tra các đường xử lý quan trọng trước khi kết luận ứng dụng tương thích.

## 3. Class-file version và giới hạn của JVM

Mỗi file `.class` có major version thể hiện phiên bản class-file format mà compiler tạo ra. JVM phải hỗ trợ major version của class file thì mới có thể nạp class đó.

Một số mốc thường gặp:

| Phiên bản Java | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ, class file có major version `65` là class file của Java 21. JVM Java 21 hỗ trợ định dạng này; JVM Java 17 không hỗ trợ class file Java 21 và thường báo `UnsupportedClassVersionError` khi cố nạp class đó.

Có thể xem major version bằng `javap`:

```bash
javap -verbose -classpath app.jar com.example.Main
```

Trong output, tìm dòng `major version`. Nếu cần kiểm tra một class file cụ thể, có thể truyền đường dẫn file `.class` cho `javap -verbose`.

Class-file version chỉ cho biết định dạng bytecode. Nó không chứng minh ứng dụng chỉ dùng API của phiên bản đó, không xác nhận dependency tương thích và không bảo đảm hành vi runtime giống nhau giữa các phiên bản JDK.

## 4. Biên dịch bằng `javac --release 21`

`--release 21` yêu cầu compiler biên dịch source theo quy tắc ngôn ngữ Java 21, tạo class file tương thích Java 21 và giới hạn API Java SE có thể sử dụng ở phiên bản 21.

Ví dụ:

```bash
javac --release 21 -d out src/com/example/Main.java
java -cp out com.example.Main
```

Khi dùng JDK 21, `javac --release 21` tạo class file major version 65. Source có thể sử dụng cú pháp Java 21 và các API Java SE đã có đến Java 21, tùy điều kiện module và dependency của project.

Nếu source gọi API chỉ xuất hiện sau Java 21, compiler sẽ báo lỗi khi biên dịch với `--release 21`, kể cả khi JDK dùng để build mới hơn và có API đó trong runtime của chính compiler.

`--release` là lựa chọn phù hợp khi cần kiểm soát đồng thời language level, class-file target và API platform. Với project Maven hoặc Gradle, hãy cấu hình release option tương ứng trong compiler plugin thay vì chỉ dựa vào JDK đang chạy build.

## 5. Vì sao `-source` và `-target` riêng lẻ chưa đủ?

Hai tùy chọn này kiểm soát hai phần khác nhau:

- `-source N` giới hạn cú pháp/ngôn ngữ ở phiên bản N.
- `-target N` yêu cầu tạo class file tương thích với target N.

Nhưng chỉ đặt `-source 17 -target 17` khi chạy compiler JDK 21 không tự giới hạn API mà source có thể gọi. Mã nguồn có thể vô tình tham chiếu API mới hơn Java 17, biên dịch thành công nhưng ném `NoSuchMethodError` hoặc `NoClassDefFoundError` khi chạy trên Java 17.

`--release 17` giải quyết vấn đề đó bằng cách giới hạn cả API Java SE được phép sử dụng khi biên dịch:

```bash
# Chỉ giới hạn source syntax và class-file target:
javac -source 17 -target 17 -d out src/com/example/Main.java

# Giới hạn source, target và Java SE API ở Java 17:
javac --release 17 -d out src/com/example/Main.java
```

Không kết hợp `--release` với `-source` hoặc `-target` trong cùng lệnh. Chọn một cách cấu hình rõ ràng; với compiler JDK 9 trở lên, ưu tiên `--release` khi cần cross-compile theo một phiên bản Java cụ thể.

## 6. `--release 21` không phải cách kiểm tra chạy trên JDK 21

Giả sử một ứng dụng hiện đang được build với target Java 17 và cần nâng runtime lên Java 21. Có thể triển khai một bước kiểm tra runtime mà không thay đổi compile target:

```bash
# Giữ artifact đã build cho Java 17.
java -version
java -jar application.jar
```

Sau đó, nếu mục tiêu dự án là chuyển compile target lên Java 21, thay đổi build để dùng release 21 và biên dịch lại:

```bash
javac --release 21 -d out src/com/example/Main.java
```

Hai bước này tạo ra hai loại bằng chứng:

| Kiểm tra | Điều được xác nhận |
|---|---|
| Chạy artifact cũ trên JVM 21 | Bytecode và các đường thực thi đã kiểm tra hoạt động trên runtime Java 21 |
| Biên dịch source bằng `--release 21` | Source dùng cú pháp và API Java SE phù hợp Java 21; output là class file Java 21 |
| Chạy artifact vừa build trên JVM 21 | Artifact mới có thể được nạp và chạy trong runtime được kiểm tra |

Không thay thế bước runtime test bằng compile test. Compiler không thể phát hiện mọi thay đổi hành vi, cấu hình, quyền truy cập, native library hoặc lỗi chỉ xuất hiện khi ứng dụng chạy.

## 7. Chọn `--release` theo phiên bản runtime tối thiểu cần hỗ trợ

Nếu ứng dụng cần chạy trên Java 21 và không cần hỗ trợ runtime cũ hơn, `--release 21` là lựa chọn phù hợp. Nếu cùng một artifact phải chạy trên Java 17 và Java 21, hãy biên dịch bằng `--release 17` và kiểm thử trên cả hai runtime.

| Mục tiêu phát hành | Compile target gợi ý | Runtime tối thiểu |
|---|---|---|
| Chỉ hỗ trợ Java 21 | `--release 21` | Java 21 |
| Hỗ trợ Java 17 và Java 21 bằng cùng artifact | `--release 17` | Java 17 |
| Hỗ trợ Java 11, 17 và 21 bằng cùng artifact | `--release 11` nếu source/dependency tương thích | Java 11 |

Không chọn release target chỉ vì build server đang cài JDK đó. Hãy căn cứ vào runtime tối thiểu mà người dùng hoặc môi trường triển khai cần hỗ trợ.

`--release` chỉ giới hạn API nền tảng Java SE. Nó không tự kiểm tra API của thư viện bên thứ ba. Nếu dependency mới chỉ hỗ trợ Java 21, artifact có thể vẫn không chạy trên Java 17 dù source được biên dịch với `--release 17` nếu build không kiểm tra bytecode/dependency tương ứng.

## 8. Những thay đổi runtime có thể xuất hiện dù bytecode cũ vẫn nạp được

Tương thích class-file không đồng nghĩa tương thích hành vi. Khi chạy ứng dụng cũ trên JDK 21, cần kiểm tra các khu vực sau:

- **API đã bị loại bỏ hoặc thay đổi:** code có thể gọi API không còn tồn tại hoặc có hành vi khác.
- **Strong encapsulation:** truy cập reflective vào JDK internals có thể bị chặn; không nên phụ thuộc vào package nội bộ của JDK.
- **Security và TLS:** mặc định thuật toán, cipher suite, certificate hoặc chính sách bảo mật có thể khác so với runtime cũ.
- **Locale, timezone và Unicode data:** dữ liệu nền có thể thay đổi giữa các bản JDK.
- **Garbage collector và memory behavior:** collector mặc định, heap ergonomics và timing có thể ảnh hưởng latency/throughput.
- **Native library:** JNI/JNA hoặc thư viện phụ thuộc hệ điều hành/kiến trúc cần được xác minh trên runtime và môi trường mới.
- **Dependency/framework:** phiên bản thư viện có thể không hỗ trợ Java 21 hoặc có thay đổi cấu hình riêng.

Không cần thay toàn bộ code chỉ vì JDK mới có API mới. Hãy dựa trên lỗi thực tế, cảnh báo migration và nhu cầu sử dụng tính năng Java 21.

## 9. Kiểm tra dependency và sử dụng JDK internals

`jdeps` giúp phân tích dependency và phát hiện một số trường hợp ứng dụng phụ thuộc vào JDK internal API:

```bash
jdeps --jdk-internals application.jar
```

Nếu công cụ báo ứng dụng phụ thuộc package nội bộ, hãy thay bằng API Java SE được hỗ trợ hoặc thư viện công khai phù hợp. Không xem các cờ mở encapsulation nội bộ là giải pháp migration lâu dài.

Để kiểm tra dependency cần phiên bản class file nào, có thể phân tích JAR bằng `jdeps` và kiểm tra class file bằng `javap`. Kết quả cần được kết hợp với tài liệu tương thích chính thức của framework/thư viện đang dùng.

`jdeps` là công cụ phân tích tĩnh. Nó không chứng minh mọi đường code có thể chạy và không phát hiện mọi lỗi reflection động, service loading, native library hoặc cấu hình runtime.

## 10. Multi-release JAR và lựa chọn class theo runtime

Một multi-release JAR có thể chứa nhiều implementation của cùng một class cho các phiên bản Java khác nhau trong các thư mục như `META-INF/versions/17` hoặc `META-INF/versions/21`. Khi chạy trên JDK hỗ trợ multi-release JAR, runtime chọn implementation phù hợp với phiên bản Java đang chạy, nếu manifest khai báo `Multi-Release: true`.

Điều này có nghĩa cùng một JAR có thể chứa class nền tương thích runtime cũ và implementation tối ưu cho Java mới. Khi kiểm tra migration, hãy chạy chính artifact multi-release trên JDK 21; chỉ giải nén và kiểm tra class nền có thể không phản ánh class thực tế được runtime chọn.

Không tự tạo multi-release JAR nếu không có nhu cầu duy trì nhiều implementation. Nếu sử dụng, cần kiểm tra build, manifest, class-file version và test trên từng runtime mục tiêu.

## 11. Quy trình migration thực tế

Một quy trình kiểm tra có thể chia thành các bước:

1. **Ghi baseline:** phiên bản JDK build hiện tại, compile target, runtime production, dependency và JVM flags.
2. **Chạy artifact hiện tại trên JDK 21:** xác nhận runtime có thể khởi động và chạy các smoke test.
3. **Chạy test tích hợp:** tập trung vào database, HTTP/TLS, serialization, reflection, native code, scheduling và các luồng nghiệp vụ chính.
4. **Phân tích cảnh báo:** dùng `jdeps --jdk-internals`, log runtime và cảnh báo từ framework/dependency.
5. **Quyết định compile target:** chọn `--release 21` nếu artifact chỉ cần hỗ trợ Java 21; giữ release cũ nếu cần hỗ trợ runtime cũ hơn.
6. **Biên dịch lại:** dùng compiler/build tool được cấu hình release rõ ràng.
7. **Kiểm tra class-file version:** dùng `javap -verbose` hoặc công cụ build để xác nhận output.
8. **Chạy artifact mới trên runtime mục tiêu:** chạy test, smoke test, load test và quan sát lỗi/hiệu năng.
9. **Triển khai theo giai đoạn:** theo dõi log, metrics, latency, throughput và khả năng rollback.

Giữ riêng kết quả của bước chạy artifact cũ và bước chạy artifact được biên dịch lại. Nếu gộp hai thay đổi vào cùng một lần mà không có baseline, sẽ khó xác định lỗi đến từ runtime mới hay bytecode/source mới.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ chạy được JAR cũ trên JDK 21 nghĩa là source đã tương thích Java 21 | Chưa kiểm tra compile hoặc API mới | Phân biệt runtime test và compile test |
| Nghĩ dùng JDK 21 build thì artifact tự chạy trên Java 21 | Target thực tế có thể vẫn cũ hoặc được cấu hình khác | Kiểm tra `--release` và major version của class file |
| Dùng `-source`/`-target` mà không giới hạn API | Có thể gọi API mới hơn runtime mục tiêu | Dùng `--release` |
| Dùng `--release 21` nhưng muốn chạy artifact trên Java 17 | Class file/API có thể vượt khả năng Java 17 | Biên dịch `--release 17` nếu Java 17 là runtime tối thiểu |
| Chỉ kiểm tra class-file major version | Bỏ sót lỗi hành vi, reflection, dependency và native code | Chạy test trên runtime mục tiêu và phân tích dependency |
| Nghĩ compile thành công bảo đảm production chạy được | Compile không kiểm tra đầy đủ cấu hình và hành vi runtime | Thực hiện integration, smoke và load test |
| Bỏ qua compile target của thư viện bên thứ ba | Dependency có thể yêu cầu JDK mới hơn | Kiểm tra metadata, tài liệu và class-file version của dependency |

## 13. Checklist nâng cấp lên Java 21

Trước khi phát hành, hãy xác nhận:

1. Đã biết chính xác JDK đang dùng để build và runtime đang dùng để chạy chưa?
2. Artifact hiện tại có được chạy thử trên JVM Java 21 chưa?
3. Compile target hiện tại và runtime tối thiểu cần hỗ trợ đã được xác định chưa?
4. Nếu chỉ hỗ trợ Java 21, build đã cấu hình `--release 21` hoặc release option tương ứng chưa?
5. Nếu vẫn hỗ trợ runtime cũ, `--release` có giữ ở phiên bản thấp nhất cần hỗ trợ không?
6. Class-file major version của artifact có khớp mục tiêu không?
7. API Java SE và dependency có nằm trong phạm vi runtime mục tiêu không?
8. Đã kiểm tra JDK internals, reflection, security/TLS và native library chưa?
9. Đã chạy test tích hợp trên JDK 21 với cấu hình gần production chưa?
10. Đã theo dõi metrics và chuẩn bị phương án rollback chưa?

## Kết luận

Chạy mã hiện có trên JDK 21 là kiểm tra khả năng tương thích runtime của bytecode, dependency và hành vi ứng dụng. Biên dịch bằng `--release 21` là quyết định tạo artifact hướng tới Java 21: compiler kiểm soát cú pháp, class-file target và API Java SE được phép sử dụng. Hai việc bổ sung cho nhau nhưng không thay thế nhau. Khi nâng cấp, hãy chạy artifact cũ trên runtime mới trước, xác định runtime tối thiểu cần hỗ trợ, chọn release target phù hợp, biên dịch lại và kiểm thử artifact mới trong điều kiện triển khai thực tế.
