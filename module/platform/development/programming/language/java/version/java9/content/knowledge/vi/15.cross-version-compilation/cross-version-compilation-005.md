# Giới hạn kiểm tra thư viện bên thứ ba khi đánh giá tương thích Java

## 1. Mục tiêu và phạm vi

Khi nâng cấp ứng dụng lên một phiên bản JDK mới, cần xác định các thư viện bên thứ ba có phụ thuộc vào API, lớp hoặc hành vi của JDK hay không. Việc kiểm tra này giúp phát hiện sớm một số rủi ro về biên dịch, liên kết và hệ thống module.

`jdeps` là công cụ phân tích phụ thuộc tĩnh đi kèm JDK. Công cụ đọc bytecode trong class hoặc JAR để xây dựng quan hệ phụ thuộc giữa lớp, package và module. Tùy chọn của `jdeps` có thể giúp tìm tham chiếu tới API nội bộ của JDK, lớp phụ thuộc không tìm thấy và các module cần thiết.

Phạm vi của `jdeps` là những gì có thể suy ra từ bytecode và đầu vào được cung cấp. Kết quả của nó không phải chứng nhận rằng một thư viện tương thích hoàn toàn với JDK đích. Cần kết hợp phân tích tĩnh với kiểm tra dependency và chạy thử ứng dụng.

## 2. Những gì có thể kiểm tra bằng jdeps

- `--recursive`: mở rộng phân tích theo các phụ thuộc có thể phân giải được, thay vì chỉ xem trực tiếp một artifact.
- `--class-path`: cung cấp các JAR hoặc thư mục cần thiết khi ứng dụng sử dụng classpath.
- `--module-path`: cung cấp các module khi ứng dụng được phân giải theo module path.
- `--jdk-internals`: tìm tham chiếu tới API nội bộ của JDK. Đây là tín hiệu cần xem xét vì API nội bộ không có cam kết tương thích như API Java được hỗ trợ công khai.
- `--missing-deps`: báo các phụ thuộc lớp không phân giải được trong tập đầu vào hiện tại.
- `--multi-release <version>`: chọn phiên bản class phù hợp khi phân tích một multi-release JAR. Giá trị cần khớp với phiên bản Java mục tiêu; chỉ dùng khi artifact có cấu trúc multi-release.

Ví dụ phân tích một ứng dụng chạy theo classpath trên Linux hoặc macOS:

```bash
jdeps --recursive --jdk-internals --missing-deps \
  --class-path "lib/a.jar:lib/b.jar" \
  app.jar
```

Trên Windows, dấu phân cách các mục trong classpath là dấu chấm phẩy (`;`) thay cho dấu hai chấm (`:`). Hãy đưa vào classpath đầy đủ các thư viện mà ứng dụng thực sự sử dụng. Nếu triển khai theo module path, cung cấp module path tương ứng thay vì mô phỏng sai cách chạy thực tế.

Nên dùng bản `jdeps` thuộc JDK mục tiêu để phân tích và ghi lại phiên bản công cụ. Với multi-release JAR, chỉ định đúng phiên bản đích bằng `--multi-release`; nếu phân tích nhầm biến thể class, báo cáo có thể không phản ánh mã sẽ được nạp ở môi trường triển khai.

## 3. Những giới hạn quan trọng

### 3.1. Không quan sát được đầy đủ hành vi nạp lớp động

`jdeps` chủ yếu đọc tham chiếu có thể nhận diện trong bytecode. Một số ứng dụng chỉ xác định lớp hoặc implementation khi chạy, ví dụ:

- `Class.forName()` nhận tên lớp từ cấu hình, cơ sở dữ liệu hoặc đầu vào người dùng.
- Reflection hoặc `MethodHandles` tạo lời gọi dựa trên tên lớp, tên method hay metadata được tính ở runtime.
- Framework quét package, đăng ký plugin, dependency injection hoặc tải provider dựa trên cấu hình.
- Mã được sinh trong lúc chạy, classloader tùy chỉnh hoặc plugin được nạp từ thư mục bên ngoài.

Những tham chiếu chỉ xuất hiện dưới dạng chuỗi, cấu hình hoặc quyết định runtime có thể không được thể hiện thành cạnh phụ thuộc tĩnh mà `jdeps` nhận diện được. Một khai báo `uses` hoặc `provides` trong module descriptor có thể cung cấp thông tin tĩnh hữu ích, nhưng không bảo đảm mọi provider và đường nạp được cấu hình lúc chạy đều nằm trong báo cáo.

Vì vậy, kết quả không có phụ thuộc không chứng minh rằng ứng dụng không nạp thêm lớp ở runtime. Cần chạy các luồng chức năng có sử dụng reflection, plugin, provider và cấu hình động.

### 3.2. Không phân tích đầy đủ mã native và môi trường hệ điều hành

Thư viện Java có thể gọi mã native qua JNI, JNA hoặc một lớp trung gian khác. `jdeps` không thay thế việc kiểm tra file native, thư viện hệ điều hành, kiến trúc CPU, ABI, biến môi trường hay đường dẫn tìm thư viện native.

Một JAR có thể không có vấn đề về phụ thuộc bytecode nhưng vẫn thất bại khi chạy do thiếu thư viện native, dùng sai kiến trúc, khác phiên bản runtime native hoặc không tương thích với hệ điều hành mục tiêu. Các phần này phải được kiểm tra trên môi trường triển khai thực tế.

### 3.3. Báo cáo phụ thuộc bị ảnh hưởng bởi độ đầy đủ của đầu vào

`jdeps` chỉ phân tích những artifact và đường dẫn mà lệnh cung cấp hoặc công cụ có thể phân giải. Nếu thiếu JAR phụ thuộc, thư viện runtime, plugin, thư viện do application server cung cấp hoặc dependency tùy chọn, báo cáo có thể xuất hiện phụ thuộc không tìm thấy hoặc bỏ sót quan hệ cần xem xét.

Phân tích một JAR đơn lẻ không tương đương phân tích toàn bộ ứng dụng. Cần xác định dependency graph đã resolve theo đúng profile, scope và môi trường build/triển khai. Đặc biệt, dependency chỉ được nạp ở runtime có thể không nằm trong tập JAR dùng lúc biên dịch.

### 3.4. Không chứng minh tương thích nhị phân hoặc tương thích hành vi

Nhìn thấy quan hệ phụ thuộc giữa hai lớp hoặc hai package không chứng minh rằng mọi method được gọi đều còn tồn tại, có cùng chữ ký hoặc giữ nguyên hành vi ở phiên bản thư viện mới. `jdeps` cũng không xác nhận hợp đồng API, kết quả nghiệp vụ, hiệu năng, bảo mật hay tính đúng đắn của ứng dụng.

Ví dụ, một thư viện có thể vẫn tham chiếu được tới các lớp cần thiết nhưng thay đổi cách xử lý TLS, serialization, charset, timezone, concurrency hoặc cấu hình mặc định. Đây là thay đổi hành vi cần được phát hiện bằng tài liệu phát hành của nhà cung cấp và kiểm thử trên JDK đích.

### 3.5. Không thay thế kiểm tra phiên bản và hỗ trợ của nhà cung cấp

`jdeps` không phải dependency resolver, công cụ kiểm tra lỗ hổng bảo mật hay cơ sở dữ liệu về ma trận hỗ trợ JDK của từng thư viện. Nó không tự xác nhận phiên bản artifact đang dùng còn được bảo trì, có bản vá bảo mật hay được nhà cung cấp hỗ trợ trên JDK đích.

Cần đối chiếu phiên bản thực tế trong dependency graph với release notes, tài liệu tương thích và thông báo bảo mật của dự án hoặc nhà cung cấp thư viện. Việc không có tham chiếu tới API nội bộ của JDK không đồng nghĩa thư viện đã được chứng nhận hỗ trợ phiên bản Java mới.

### 3.6. Artifact đóng gói hoặc biến đổi có thể làm khó việc truy vết

JAR đã shade, relocate, obfuscate hoặc gộp nhiều dependency có thể làm tên package và ranh giới artifact khác với dependency graph ban đầu. Class được sinh trong build, được tải từ vị trí ngoài gói hoặc được thay thế theo cấu hình cũng có thể không nằm trong tập phân tích.

Với multi-release JAR, các phiên bản class khác nhau có thể được chọn theo JDK chạy ứng dụng. Cần phân tích đúng biến thể mục tiêu bằng `--multi-release <version>`; phân tích một biến thể không đại diện cho mọi JDK mà artifact hỗ trợ.

## 4. Quy trình kiểm tra đáng tin cậy

1. **Chốt môi trường mục tiêu.** Ghi rõ phiên bản JDK, hệ điều hành, kiến trúc, cách triển khai và ứng dụng chạy theo classpath hay module path.
2. **Lập danh sách dependency đã resolve.** Lấy dependency tree từ công cụ build, kiểm tra đúng phiên bản, scope, dependency bắc cầu, dependency tùy chọn, plugin và thư viện được cung cấp bởi môi trường triển khai. Giữ lại lockfile hoặc thông tin phiên bản để có thể tái lập kết quả.
3. **Phân tích bằng jdeps với đầu vào đầy đủ.** Phân tích artifact của ứng dụng và các thư viện liên quan. Cung cấp đúng classpath hoặc module path; dùng `--recursive`, `--jdk-internals` và `--missing-deps` khi phù hợp. Với multi-release JAR, chọn đúng phiên bản đích.
4. **Phân loại từng phát hiện.** Với phụ thuộc không tìm thấy, xác định đó là thiếu JAR, dependency chỉ có ở runtime, dependency tùy chọn hay tham chiếu động. Với API nội bộ, xác định thư viện nào tạo tham chiếu và tìm phiên bản thay thế có hỗ trợ API công khai.
5. **Biên dịch và kiểm thử trên JDK đích.** Chạy unit test, integration test, kiểm thử khởi động và các luồng có dùng reflection, plugin, ServiceLoader, JNI hoặc cấu hình động. Kiểm thử với đúng gói đã build và cấu hình gần môi trường triển khai.
6. **Đối chiếu hỗ trợ và bảo mật.** Kiểm tra release notes, ma trận hỗ trợ JDK, trạng thái bảo trì và bản vá bảo mật của từng thư viện quan trọng. Cập nhật dependency khi cần rồi chạy lại toàn bộ kiểm tra.
7. **Lưu bằng chứng.** Ghi lại phiên bản JDK và `jdeps`, lệnh đã chạy, dependency graph, phiên bản artifact, báo cáo và kết quả test. Nhờ đó có thể so sánh khi nâng cấp JDK hoặc thư viện lần tiếp theo.

## 5. Cách diễn giải kết quả

| Kết quả | Cách hiểu đúng | Việc cần làm |
|---|---|---|
| Có tham chiếu tới API nội bộ JDK | Có rủi ro phụ thuộc vào API không được bảo đảm tương thích | Xác định artifact và thay bằng API công khai hoặc phiên bản thư viện đã xử lý |
| Có missing dependency | Tập đầu vào hiện tại không phân giải được một lớp được tham chiếu | Kiểm tra classpath/module path, dependency runtime và cách đóng gói |
| Có cạnh phụ thuộc giữa các module | Công cụ đã nhận diện quan hệ phụ thuộc tĩnh | Đánh giá module descriptor, module path và quyền truy cập cần thiết |
| Không có cảnh báo | Không phát hiện vấn đề thuộc phạm vi phân tích với đầu vào hiện tại | Vẫn phải kiểm tra hành vi động, native code, hỗ trợ phiên bản và chạy test |

Một dòng phụ thuộc trong báo cáo không tự động có nghĩa là lỗi tương thích; nó cho biết có quan hệ cần đánh giá. Ngược lại, báo cáo sạch chỉ có ý nghĩa đối với bytecode, artifact và đường dẫn đã được phân tích. Không dùng riêng kết quả `jdeps` để kết luận một thư viện đã sẵn sàng cho JDK mới.

## 6. Checklist trước khi kết luận

- [ ] Đã dùng `jdeps` từ JDK mục tiêu và ghi lại phiên bản công cụ.
- [ ] Đã phân tích đúng artifact và phiên bản dependency thực tế.
- [ ] Classpath hoặc module path phản ánh cách ứng dụng được triển khai.
- [ ] Đã xem xét `--jdk-internals` và `--missing-deps`.
- [ ] Multi-release JAR được phân tích theo đúng phiên bản Java đích.
- [ ] Đã kiểm tra reflection, plugin, provider, classloader và cấu hình động bằng test runtime.
- [ ] Đã kiểm tra JNI/JNA, thư viện native, hệ điều hành và kiến trúc mục tiêu.
- [ ] Đã đối chiếu tài liệu hỗ trợ, release notes và bản vá bảo mật của nhà cung cấp.
- [ ] Ứng dụng đã được biên dịch và chạy integration test trên JDK đích.

## 7. Kết luận

`jdeps` là công cụ hữu ích để nhìn thấy phụ thuộc tĩnh và phát hiện một số rủi ro liên quan đến API nội bộ hoặc lớp không phân giải được. Giới hạn chính của nó là không thực thi ứng dụng và không quan sát đầy đủ các quyết định nạp lớp, mã native hay thay đổi hành vi ở runtime.

Đánh giá thư viện bên thứ ba cần kết hợp ba nguồn bằng chứng: phân tích bytecode với `jdeps`, kiểm tra dependency và chính sách hỗ trợ của nhà cung cấp, cùng kiểm thử ứng dụng trên JDK và môi trường triển khai mục tiêu. Chỉ khi các bước này đều đạt yêu cầu mới có cơ sở kết luận mức độ tương thích.