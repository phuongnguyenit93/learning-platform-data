# Triển khai thay đổi mã và khuôn mẫu đồng bộ

## Mục tiêu

Trong ứng dụng MVC, một thay đổi giao diện thường liên quan đồng thời đến Controller, Model hoặc application service, View template, DTO, cấu hình và tài nguyên tĩnh. Nếu chỉ cập nhật một phần, người dùng có thể nhận HTML mới nhưng server cũ không hiểu dữ liệu gửi lên, hoặc server mới render một template cũ đang thiếu trường cần thiết. Khi ứng dụng chạy nhiều instance, mỗi instance còn có thể phục vụ một phiên bản mã hoặc khuôn mẫu khác nhau trong cùng thời điểm.

Triển khai đồng bộ là quá trình đưa các thành phần có liên quan vào môi trường chạy theo một phiên bản tương thích, có kiểm soát và có khả năng quan sát. Với MVC, bài học này dùng từ khuôn mẫu để chỉ các View template như Thymeleaf hoặc JSP, cùng CSS, JavaScript, ảnh và tài nguyên mà View tham chiếu.

Bài học trình bày cách đóng gói và phát hành artifact, quản lý tương thích giữa code và template, cập nhật nhiều instance, xử lý cache, migration dữ liệu, rollback và theo dõi sau triển khai. Ví dụ sử dụng Java, Spring và một pipeline CI/CD điển hình.

Sau khi học, người học có thể:

- Giải thích vì sao code, View template, static assets và cấu hình phải tương thích.
- Thiết kế artifact bất biến và quy trình build một lần, triển khai nhiều môi trường.
- Chọn chiến lược rolling, blue-green hoặc canary phù hợp.
- Giữ khả năng tương thích giữa phiên bản cũ và mới trong giai đoạn rollout.
- Đồng bộ template, static assets và cache giữa nhiều instance.
- Triển khai database migration theo hướng tương thích ngược.
- Lập kế hoạch rollback hoặc forward-fix.
- Dùng health check, log, metric và trace để xác nhận release hoạt động đúng.

## 1. Triển khai đồng bộ có nghĩa gì trong MVC?

Một chức năng MVC thường đi qua nhiều thành phần:

    Browser
       |
       | HTTP request
       v
    Controller
       |
       v
    Application Service / Model
       |
       v
    Repository / Database
       |
       v
    Controller
       |
       v
    View Template
       |
       +---- HTML
       +---- CSS / JavaScript / Image
       |
       v
    Browser

Ví dụ, một thay đổi thêm trường trạng thái đăng ký có thể tác động đến:

- Domain model hoặc query projection cung cấp trạng thái.
- Application service và response model.
- Controller đưa dữ liệu vào Model của View.
- Template hiển thị trạng thái.
- CSS tạo kiểu cho nhãn trạng thái.
- JavaScript xử lý thao tác mới.
- Database migration thêm hoặc chuyển đổi dữ liệu.
- Cache và tài nguyên tĩnh được phân phối qua CDN hoặc reverse proxy.

Nếu template mới dùng thuộc tính registrationStatus nhưng Controller cũ chưa đưa thuộc tính đó vào Model, View có thể hiển thị trống hoặc phát sinh lỗi. Nếu Controller mới yêu cầu một trường bắt buộc nhưng template cũ không gửi, request có thể thất bại. Nếu JavaScript mới gọi endpoint chưa được triển khai, giao diện có thể hoạt động không ổn định.

Vì vậy, đồng bộ không chỉ là chép các file cùng lúc. Nó là bảo đảm hợp đồng giữa các thành phần vẫn đúng trong suốt quá trình chuyển phiên bản.

### Ba lớp cần đồng bộ

| Lớp | Ví dụ | Rủi ro khi lệch phiên bản |
|---|---|---|
| Runtime code | Controller, service, domain, serializer | Endpoint hoặc hành vi xử lý không tương thích |
| Presentation assets | Thymeleaf/JSP, CSS, JavaScript, ảnh | View thiếu dữ liệu, asset cũ hoặc script gọi API sai |
| Data and configuration | Schema, migration, feature flag, config | Code không đọc được schema hoặc cấu hình mới |

Không phải mọi thay đổi đều chạm cả ba lớp. Hãy xác định tập thành phần thực sự liên quan trong mỗi release và kiểm tra tương thích của chúng.

## 2. Xác định đơn vị phát hành

Đơn vị phát hành (release unit) là tập hợp những thành phần được kiểm thử và triển khai như một phiên bản có thể nhận diện.

Với ứng dụng Spring MVC đóng gói thành executable JAR, View template nằm trong classpath thường được đóng gói cùng mã ứng dụng. Khi deploy JAR mới, Controller và template trong JAR đó được thay thế cùng nhau. CSS, JavaScript và ảnh có thể cũng nằm trong JAR hoặc được build thành gói tài nguyên riêng.

Với ứng dụng triển khai nhiều gói, release unit có thể gồm:

- Application artifact: JAR, WAR hoặc image container.
- Frontend asset bundle: JavaScript, CSS, ảnh đã build.
- Template package nếu template được lưu và cập nhật độc lập.
- Database migration đã được kiểm thử.
- Configuration schema hoặc feature flag cần thiết.
- Release manifest ghi lại phiên bản và checksum của từng thành phần.

### Đóng gói template cùng ứng dụng

Đóng gói View template cùng artifact giúp code và template được phát hành như một đơn vị. Đây thường là lựa chọn đơn giản và đáng tin cậy cho ứng dụng MVC server-side.

Ưu điểm:

- Tránh tình trạng node A dùng template mới trong khi node B dùng template cũ.
- Có thể kiểm thử chính xác artifact trước khi triển khai.
- Rollback ứng dụng cũng khôi phục đúng template đi kèm.
- Không cần đồng bộ file template thủ công trên từng máy chủ.

Giới hạn:

- Thay template cũng cần build và deploy artifact mới.
- Không thể thay template tức thời nếu không triển khai ứng dụng.
- Template runtime không thể được chỉnh sửa độc lập ngoài quy trình release.

### Template được lưu bên ngoài artifact

Một số hệ thống cần cập nhật template thường xuyên hoặc cho phép người vận hành quản lý nội dung. Khi đó template có thể nằm trong object storage, shared volume hoặc một dịch vụ quản lý nội dung.

Cách này tạo thêm yêu cầu vận hành:

- Phiên bản template phải được đánh dấu và truy xuất.
- Template phải được xác thực trước khi kích hoạt.
- Mọi instance phải đọc cùng phiên bản hoặc một phiên bản tương thích.
- Cần cơ chế chuyển phiên bản nguyên tử để tránh đọc file đang ghi dở.
- Cần rollback template độc lập hoặc khôi phục đồng bộ với code.

Không nên cho phép người dùng sửa trực tiếp template thực thi tùy ý nếu template có thể truy cập dữ liệu hoặc gọi biểu thức nội bộ. Quyền sửa template cần được giới hạn và kiểm soát như một thay đổi mã.

## 3. Build một lần, triển khai cùng artifact

Một nguyên tắc quan trọng của CI/CD là build một artifact đã kiểm thử rồi promote chính artifact đó qua các môi trường. Không nên build lại riêng cho staging và production nếu điều đó có thể tạo ra nội dung khác nhau.

Quy trình tổng quát:

    Source + Dependencies
             |
             v
        CI Build
             |
             v
       Unit / MVC Tests
             |
             v
      Package Artifact
             |
             v
      Immutable Registry
             |
          +--+--+
          |     |
          v     v
       Staging Production
          |     |
          +--+--+
             |
        Verify Release

Artifact nên có version hoặc digest bất biến. Cùng một artifact đã kiểm thử ở staging cần được đưa lên production; cấu hình môi trường được inject lúc runtime theo quy trình quản lý cấu hình.

### Artifact bất biến

Không chỉnh sửa nội dung JAR, container image hoặc template package sau khi đã phát hành. Nếu cần thay đổi, tạo một artifact mới với version mới.

Lợi ích:

- Có thể xác định chính xác mã đang chạy.
- Dễ so sánh release trước và sau.
- Dễ rollback về artifact đã biết.
- Giảm khác biệt giữa môi trường.
- Có thể xác minh checksum hoặc image digest.

Không dùng tên chung như latest làm định danh duy nhất cho release đang chạy. Có thể dùng tag thuận tiện, nhưng deployment manifest cần ghi version hoặc digest cụ thể.

### Manifest release

Một manifest đơn giản có thể ghi:

    release:
      applicationVersion: 2.8.0
      imageDigest: sha256:...
      templateVersion: 2.8.0
      assetManifest: assets-2.8.0.json
      migrationVersion: 20261119_01
      commit: 4a1b2c3
      builtAt: 2026-11-19T10:00:00Z

Đây là cấu trúc minh họa. Hệ thống có thể lưu các giá trị trong deployment metadata, image labels hoặc release record. Không đưa secret, password hay token vào manifest.

### Phân biệt build-time config và runtime config

Build-time config có thể gồm compiler flags, asset hashing hoặc thông tin phiên bản. Runtime config gồm URL dịch vụ, feature flag, connection string và giới hạn vận hành theo môi trường.

Không đóng secret production vào JAR hoặc image. Dùng secret manager, environment injection hoặc cơ chế bảo mật của nền tảng triển khai.

## 4. Quản lý tương thích giữa code và View template

Trong MVC, template thường phụ thuộc vào tên thuộc tính trong Model, DTO hoặc các biến được Controller đưa vào View. Thay đổi tên, kiểu hoặc ý nghĩa thuộc tính có thể làm template cũ không còn tương thích.

Ví dụ, template cũ sử dụng:

    <span th:text="${registration.statusLabel}"></span>

Template mới có thể sử dụng:

    <span th:text="${registration.displayStatus}"></span>

Nếu Controller đổi sang chỉ cung cấp displayStatus trong khi một instance khác vẫn phục vụ template cũ cần statusLabel, trang có thể lỗi tùy node nhận request.

### Hợp đồng View Model

Hãy xem dữ liệu Controller đưa vào View là một hợp đồng:

    public record RegistrationViewModel(
            UUID id,
            String courseTitle,
            String displayStatus,
            boolean canCancel) {
    }

Controller tạo View Model theo một cấu trúc rõ ràng. Template dùng các trường đã công bố thay vì phụ thuộc trực tiếp vào entity persistence có thể thay đổi.

Lợi ích:

- Giới hạn dữ liệu được đưa vào View.
- Tách template khỏi cấu trúc database.
- Có thể thay đổi entity mà không phải sửa mọi template.
- Dễ kiểm thử rendering và tương thích.

### Thay đổi tương thích ngược

Khi rollout nhiều phiên bản cùng tồn tại, nên ưu tiên thay đổi theo trình tự:

1. Thêm thuộc tính mới trong View Model nhưng vẫn giữ thuộc tính cũ.
2. Triển khai code có thể cung cấp cả hai trường.
3. Cập nhật template để dùng trường mới.
4. Quan sát lỗi và xác nhận tất cả instance đã chuyển.
5. Chỉ loại bỏ trường cũ trong một release sau khi không còn consumer nào dùng nó.

Đây là chiến lược expand-and-contract áp dụng cho hợp đồng giữa code và View. Không xóa ngay một biến template đang được nhiều phiên bản hoặc fragment sử dụng.

### Kiểm thử template

Các test nên xác nhận:

- Controller cung cấp đủ thuộc tính cần thiết.
- Template render được với dữ liệu hợp lệ.
- Trạng thái null hoặc optional được xử lý rõ.
- Fragment dùng chung nhận đúng biến.
- Thay đổi tên trường không làm hỏng các trang liên quan.
- Nội dung không tin cậy được escape đúng ngữ cảnh.

Có thể dùng Spring MVC test để xác nhận tên view và model attributes, cùng template integration test để render template thực tế.

## 5. Đồng bộ static assets với HTML

CSS và JavaScript thường được cache lâu ở browser hoặc CDN. Nếu HTML mới tham chiếu đến file asset mới nhưng CDN chưa có file đó, người dùng có thể gặp 404. Ngược lại, HTML cũ có thể tiếp tục tham chiếu asset đã bị xóa quá sớm.

### Dùng fingerprint hoặc content hash

Thay vì ghi đè cùng một tên file như app.js, build có thể tạo tên có hash:

    app.4f83a1.js
    styles.9b2c10.css

HTML của release mới tham chiếu đúng tên file. Vì tên thay đổi theo nội dung, browser/CDN có thể cache lâu mà không nhầm phiên bản.

Quy trình nên:

1. Upload asset mới trước khi phát hành HTML tham chiếu đến chúng.
2. Xác nhận asset đã có ở origin và CDN.
3. Deploy application/template mới.
4. Giữ asset cũ đủ lâu cho browser hoặc trang cũ còn mở.
5. Xóa asset cũ theo chính sách retention sau khi chắc chắn không còn tham chiếu.

Không xóa asset cũ ngay tại thời điểm deploy nếu người dùng có thể đang mở tab với HTML phiên bản trước.

### Cache-Control

Có thể dùng chính sách khác nhau:

| Tài nguyên | Cache policy thường dùng |
|---|---|
| Asset có fingerprint | Cache dài hạn, immutable |
| HTML động | No-store hoặc revalidation theo yêu cầu dữ liệu |
| Template được render server-side | Cache ở server theo phiên bản, không cache công khai nếu chứa dữ liệu riêng tư |
| Manifest tài nguyên | Cache ngắn hoặc revalidate |
| API response riêng tư | Cache policy phù hợp quyền và dữ liệu |

Không áp dụng cache dài hạn cho HTML có dữ liệu người dùng hoặc token nhạy cảm. Cấu hình cache cần xét cả browser, reverse proxy và CDN.

## 6. Đồng bộ template cache giữa nhiều instance

Một số template engine hoặc framework cache template đã phân tích để tăng hiệu năng. Khi template được thay đổi bên ngoài artifact, mỗi instance có thể giữ bản cache riêng.

Ví dụ:

- Instance A đã nạp template version 2.8.
- Instance B vẫn giữ template version 2.7 trong cache.
- Storage đã chuyển sang version 2.8.
- Hai request giống nhau nhận HTML khác nhau tùy node.

Điều này gây khó điều tra vì lỗi có thể chỉ xuất hiện khi load balancer chuyển request sang một instance cụ thể.

### Template đóng gói trong artifact

Nếu template nằm trong JAR/image bất biến, cache gắn với vòng đời process. Triển khai instance mới sẽ nạp template đi kèm artifact mới. Cách này giảm đáng kể nhu cầu invalidation phân tán.

### Template được cập nhật độc lập

Nếu template nằm ngoài artifact, cần một chiến lược cache nhất quán:

- Key cache chứa template version.
- Thay version tạo cache namespace mới.
- Instance nhận thông báo invalidation hoặc phát hiện version mới.
- Chỉ chuyển sang template version mới sau khi file đã được xác thực và sẵn sàng.
- Có thể giữ version trước để rollback nhanh.
- Log version template trên mỗi lần render hoặc trong diagnostic context.

Không nên chỉ xóa cache cục bộ trên một node. Với nhiều instance, cần cơ chế fan-out hoặc versioned cache key để mọi node chuyển cùng một cách.

### Không đọc file đang được ghi dở

Nếu template được cập nhật qua file system, hãy ghi vào file tạm, validate hoàn tất rồi đổi tên hoặc cập nhật pointer theo thao tác nguyên tử được hệ thống lưu trữ hỗ trợ. Đừng ghi đè từng byte lên file mà request đang render.

Với object storage, có thể upload object version mới rồi cập nhật một manifest hoặc pointer sau khi object đã sẵn sàng. Mỗi instance cần đọc một version cụ thể thay vì đoán file mới nhất.

## 7. Chiến lược triển khai nhiều instance

Ứng dụng MVC thường chạy nhiều instance sau load balancer. Chiến lược rollout quyết định cách phiên bản cũ và mới cùng tồn tại.

### Rolling deployment

Rolling deployment lần lượt thay từng instance:

    v1  v1  v1  v1
     |   |
     v   v
    v2  v1  v1  v1
    v2  v2  v1  v1
    v2  v2  v2  v1
    v2  v2  v2  v2

Ưu điểm:

- Không cần nhân đôi toàn bộ môi trường.
- Có thể duy trì dịch vụ khi thay từng node.
- Tài nguyên triển khai được dùng dần.

Rủi ro:

- Phiên bản v1 và v2 cùng nhận request trong thời gian rollout.
- Session hoặc cache có thể được dùng bởi cả hai phiên bản.
- Code, template và database phải tương thích trong giai đoạn chuyển tiếp.
- Asset mới phải có sẵn trước khi HTML mới tham chiếu.

Rolling deployment phù hợp khi phiên bản cũ và mới có thể cùng hoạt động trong một khoảng thời gian.

### Blue-green deployment

Blue-green duy trì hai môi trường:

- Blue: phiên bản đang phục vụ.
- Green: phiên bản mới đã được triển khai và kiểm tra.

Sau khi Green đạt readiness, traffic được chuyển sang Green. Nếu có vấn đề, có thể chuyển traffic về Blue.

Ưu điểm:

- Có thể kiểm tra môi trường mới trước khi nhận traffic thật.
- Chuyển traffic nhanh.
- Rollback ứng dụng thường đơn giản hơn rolling.

Rủi ro:

- Cần tài nguyên cho hai môi trường.
- Cả hai môi trường có thể dùng chung database nên migration vẫn phải tương thích.
- Session, upload và cache dùng chung cần được thiết kế rõ.
- Chuyển traffic không tự động rollback các thay đổi dữ liệu đã commit.

### Canary deployment

Canary đưa phiên bản mới đến một tỷ lệ nhỏ traffic hoặc một nhóm người dùng trước:

    Traffic 100%
       |
       +---- 95% ----> v1
       |
       +----  5% ----> v2

Theo dõi error rate, latency, business metrics và log theo release. Nếu ổn định, tăng dần tỷ lệ traffic; nếu không, dừng rollout hoặc chuyển traffic về phiên bản cũ.

Canary hữu ích khi cần xác nhận hành vi trên traffic thật, nhưng phải bảo đảm dữ liệu và tác dụng phụ không bị thực hiện hai lần khi retry hoặc chuyển node.

### Chọn chiến lược

| Tiêu chí | Rolling | Blue-green | Canary |
|---|---|---|---|
| Tài nguyên | Vừa phải | Cao hơn | Tùy cách phân luồng |
| Chuyển traffic | Từng node | Chuyển toàn môi trường | Tăng dần |
| Phát hiện lỗi | Trong quá trình rollout | Qua kiểm tra trước và sau switch | Trên một phần traffic thật |
| Yêu cầu tương thích cũ/mới | Cao trong rollout | Vẫn cần nếu dùng chung database/session | Cao trong thời gian song song |
| Rollback | Redeploy phiên bản cũ | Chuyển traffic về môi trường cũ | Dừng hoặc giảm traffic mới |

Không có một chiến lược phù hợp cho mọi ứng dụng. Chọn dựa trên khả năng tương thích, mức độ quan trọng, thời gian gián đoạn chấp nhận được và năng lực vận hành.

## 8. Giữ tương thích trong thời gian hai phiên bản cùng chạy

Trong rolling hoặc canary, request có thể đến phiên bản cũ hoặc mới. Người dùng có thể mở form bằng v1 rồi submit đến v2. Hoặc form được render bởi v2 nhưng request tiếp theo lại đến v1.

Một số nguyên tắc:

- Giữ endpoint cũ hoạt động trong thời gian chuyển tiếp.
- Thêm trường mới theo cách optional trước khi bắt buộc.
- Không đổi semantics của trường đang được client sử dụng mà không có versioning.
- Duy trì khả năng đọc dữ liệu do phiên bản cũ ghi.
- Duy trì khả năng xử lý form đã mở trước khi deploy.
- Tránh thay đổi session serialization không tương thích nếu session được chia sẻ.
- Giữ asset cũ cho các tab trình duyệt còn mở.

### HTML form và phiên bản server

Một form HTML có thể tồn tại trong browser nhiều giờ. Sau khi deploy, người dùng submit form được render từ template cũ. Nếu server mới đã xóa field hoặc thay đổi CSRF/session handling, request có thể thất bại.

Hãy cân nhắc:

- Duy trì tên field cũ trong giai đoạn chuyển tiếp.
- Chấp nhận giá trị cũ và mới khi hợp lý.
- Có cơ chế xử lý form stale hoặc optimistic version.
- Trả lỗi thân thiện nếu trạng thái tài nguyên đã thay đổi.
- Không giả định mọi form đang mở đều được render từ phiên bản hiện tại.

### Session compatibility

Nếu session được serialize vào Redis hoặc database, thay đổi class session, principal hoặc attribute có thể làm phiên bản mới không đọc được session cũ. Khi rolling deploy, hai phiên bản cần tương thích schema session hoặc có chiến lược session migration/expiration.

Một cách đơn giản hơn có thể là giữ session schema ổn định qua release, hoặc buộc người dùng đăng nhập lại trong một release có kế hoạch rõ ràng. Không nên để lỗi deserialization bất ngờ xảy ra sau khi rollout.

## 9. Database migration phải tương thích với code rollout

Database schema thường được dùng chung bởi tất cả application instance. Nếu migration phá vỡ schema mà code cũ còn chạy, rolling deploy có thể làm một phần request thất bại.

Dùng chiến lược expand-and-contract:

### Expand

1. Thêm cột hoặc bảng mới theo cách tương thích.
2. Giữ cột cũ trong thời gian chuyển tiếp.
3. Deploy code có thể đọc cả dữ liệu cũ và mới.
4. Bắt đầu ghi dữ liệu mới hoặc ghi song song khi cần.
5. Backfill dữ liệu cũ theo batch có kiểm soát.

### Migrate

1. Chuyển các luồng đọc sang cấu trúc mới.
2. Xác nhận dữ liệu đã được chuyển đủ.
3. Theo dõi lỗi và metric cho cả đường cũ/mới.
4. Dừng ghi vào cấu trúc cũ sau khi tất cả instance đã dùng đường mới.

### Contract

1. Xác nhận không còn code hoặc job nào dùng cột cũ.
2. Gỡ tham chiếu cũ trong release sau.
3. Chỉ sau đó mới xóa cột hoặc bảng cũ.

Không gộp thêm cột, đổi code và xóa cột cũ trong một migration duy nhất nếu ứng dụng cần rolling deployment. Khi rollback code, schema đã mở rộng vẫn nên tương thích với phiên bản cũ.

### Flyway hoặc Liquibase

Có thể quản lý migration bằng Flyway hoặc Liquibase. Migration nên:

- Có version hoặc identifier rõ.
- Được review cùng thay đổi code.
- Chạy trong pipeline trên database thử nghiệm.
- Có kiểm tra thời gian chạy và lock.
- Không chứa thao tác phá hủy dữ liệu ngoài kế hoạch.
- Có hướng khôi phục hoặc forward-fix được tài liệu hóa.

Không phải mọi migration đều có thể rollback bằng cách chạy ngược SQL. Khi đã ghi hoặc chuyển dữ liệu, một forward migration sửa lỗi thường an toàn hơn rollback tự động.

## 10. Đồng bộ cấu hình và feature flag

Code mới có thể cần cấu hình mới. Nếu deploy code trước khi cấu hình tồn tại, ứng dụng có thể khởi động thất bại hoặc hoạt động với giá trị mặc định không an toàn.

Quy trình nên xác định:

- Cấu hình bắt buộc và tùy chọn.
- Giá trị mặc định an toàn.
- Cách validate cấu hình khi startup.
- Nguồn cấp secret.
- Cách thay đổi cấu hình mà không restart nếu hệ thống hỗ trợ.
- Khả năng tương thích khi hai phiên bản đọc cùng cấu hình.

### Feature flag

Feature flag cho phép deploy code trước nhưng bật hành vi mới sau. Điều này tách việc phát hành mã khỏi thời điểm kích hoạt tính năng.

Ví dụ:

    if (featureFlags.isEnabled("new-registration-view", actor)) {
        return "registrations/detail-v2";
    }

    return "registrations/detail";

Feature flag hữu ích để:

- Bật tính năng cho nhóm nhỏ.
- Tắt nhanh hành vi mới nếu metric xấu.
- Thử nghiệm theo tenant hoặc user cohort.
- Tách migration dữ liệu khỏi việc hiển thị tính năng.

Tuy nhiên, flag tạo thêm nhánh cần kiểm thử. Mỗi flag cần owner, mục đích, giá trị mặc định và thời điểm dọn bỏ. Không để flag cũ tồn tại vô thời hạn.

### Secret và cấu hình nhạy cảm

Không đưa mật khẩu database, API key hoặc signing key vào template, source control hay artifact. Secret phải được cấp theo môi trường và giới hạn quyền truy cập. Khi rotation secret, cần xem xét thời gian hai phiên bản cùng chạy để cả phiên bản cũ và mới có thể chuyển đổi an toàn.

## 11. Cache dữ liệu và cache View

Ngoài template cache và browser asset cache, MVC có thể có cache cho query result, fragment hoặc response.

Rủi ro khi deploy:

- Cache chứa DTO theo schema cũ.
- Cache key không bao gồm tenant hoặc quyền.
- Instance mới đọc dữ liệu cache do instance cũ ghi với định dạng khác.
- Fragment cache chứa HTML đã render theo template cũ.
- CDN tiếp tục phục vụ HTML hoặc asset không còn tương thích.

### Version cache key

Khi cấu trúc dữ liệu cache thay đổi, có thể thêm version vào key:

    registration-view:v2:{registrationId}

Phiên bản key mới tránh deserialize nhầm cấu trúc cũ. Dữ liệu cache cũ có thể hết hạn tự nhiên hoặc được xóa theo kế hoạch.

### Cache invalidation có kiểm soát

Không xóa toàn bộ cache ngay lập tức nếu thao tác đó gây tải lớn lên database. Có thể:

- Xóa theo namespace hoặc nhóm key.
- Dùng versioned key để chuyển dần.
- Warm cache trước khi tăng traffic.
- Giới hạn concurrency của cache rebuild.
- Theo dõi cache hit rate và database load.

Với dữ liệu cá nhân, bảo đảm cache key và cache policy không cho phép user này nhận response của user khác. Test cross-user/cross-tenant sau deploy.

## 12. Quy trình CI/CD cho thay đổi MVC

Một pipeline triển khai có thể gồm các bước:

1. Kiểm tra source và dependency.
2. Compile và chạy unit test.
3. Chạy MVC/controller test và template rendering test.
4. Chạy security test cho authentication, authorization và CSRF.
5. Build asset và tạo fingerprint.
6. Đóng gói artifact bất biến.
7. Tạo manifest, checksum và release metadata.
8. Quét dependency/image và kiểm tra cấu hình.
9. Chạy migration trên môi trường thử nghiệm.
10. Deploy lên staging và chạy smoke test.
11. Xác nhận health check, log, metric và template version.
12. Triển khai production theo rolling, blue-green hoặc canary.
13. Theo dõi chỉ số và business outcome.
14. Hoàn tất rollout hoặc rollback/forward-fix theo tiêu chí đã định.

### Kiểm thử template trong pipeline

Template có thể chứa lỗi chỉ xuất hiện khi render, ví dụ biểu thức tham chiếu thuộc tính không tồn tại hoặc fragment thiếu biến. Chỉ compile Java không đủ.

Nên có test render các trang quan trọng với dữ liệu đại diện:

- Trang danh sách.
- Trang chi tiết.
- Form tạo mới và cập nhật.
- Trang lỗi.
- Trang có phân quyền khác nhau.
- Trang hỗ trợ nhiều locale.
- Fragment dùng chung như navigation hoặc sidebar.

Nếu template engine kiểm tra biểu thức ở runtime, hãy khởi tạo engine trong test và render thật để phát hiện lỗi sớm.

## 13. Triển khai an toàn với health check và graceful shutdown

Một instance mới không nên nhận traffic trước khi đã khởi động đầy đủ và có thể phục vụ request.

### Liveness và readiness

- Liveness cho biết process còn sống và không bị kẹt đến mức cần restart.
- Readiness cho biết instance đã sẵn sàng nhận traffic.
- Startup probe có thể dành thời gian cho ứng dụng khởi động hoặc nạp cấu hình.

Readiness nên kiểm tra các dependency cần thiết cho việc phục vụ request theo chính sách. Không nên đưa mọi dependency tùy chọn vào readiness nếu điều đó khiến toàn bộ cụm ngừng nhận traffic khi một tích hợp phụ bị lỗi.

### Graceful shutdown

Khi thay instance cũ:

1. Đánh dấu instance không còn ready để load balancer ngừng gửi request mới.
2. Chờ request đang xử lý hoàn tất trong giới hạn.
3. Dừng nhận công việc mới.
4. Hoàn tất hoặc chuyển giao tác vụ nền theo chính sách.
5. Đóng connection pool và tài nguyên.
6. Kết thúc process.

Với session sticky hoặc WebSocket, cần có chiến lược drain và thời gian chuyển tiếp. Không xóa session hoặc ngắt kết nối bất ngờ nếu người dùng đang thực hiện thao tác quan trọng.

## 14. Rollback và forward-fix

Rollback là đưa hệ thống trở lại một release đã biết. Forward-fix là triển khai một release mới để sửa lỗi mà không quay lại toàn bộ trạng thái cũ.

### Khi nào rollback phù hợp?

Rollback ứng dụng thường phù hợp khi:

- Artifact mới không khởi động được.
- Template mới làm lỗi phần lớn trang.
- Error rate hoặc latency vượt ngưỡng đã định.
- Một chức năng mới gây ảnh hưởng nghiêm trọng và phiên bản cũ vẫn tương thích với schema hiện tại.
- Asset mới không được phân phối đúng.

Trước khi rollback, phải xác nhận database migration và dữ liệu đã thay đổi có còn tương thích với code cũ hay không.

### Khi nào cần forward-fix?

Forward-fix có thể phù hợp khi:

- Migration đã thay đổi dữ liệu theo cách không thể đảo ngược an toàn.
- Người dùng đã tạo dữ liệu theo schema mới.
- Rollback làm mất dữ liệu hoặc làm ứng dụng cũ không đọc được.
- Lỗi có thể được sửa bằng một patch nhỏ và triển khai nhanh.

### Kế hoạch rollback

Mỗi release nên ghi:

- Artifact trước đó và digest.
- Phiên bản template và asset trước đó.
- Migration đã chạy.
- Các feature flag liên quan.
- Cấu hình đã thay đổi.
- Tác động dữ liệu có thể không đảo ngược.
- Lệnh hoặc thao tác chuyển traffic về phiên bản cũ.
- Người chịu trách nhiệm quyết định và xác nhận rollback.

Không coi việc đổi image tag là rollback hoàn chỉnh nếu CDN vẫn phục vụ asset mới, template bên ngoài vẫn ở phiên bản mới hoặc database đã bị thay đổi không tương thích.

## 15. Quan sát release sau khi triển khai

Một release thành công không chỉ là process khởi động. Cần xác nhận người dùng có thể hoàn thành use case và các thành phần liên quan đang chạy đúng phiên bản.

### Gắn release metadata vào log

Log nên có thể xác định:

- Application version hoặc release ID.
- Instance/pod ID.
- Template version nếu được quản lý riêng.
- Asset manifest version.
- Request ID hoặc trace ID.
- Route template và status code.
- Use case hoặc event liên quan.

Không ghi secret hoặc dữ liệu cá nhân vào log chỉ để xác định release.

### Theo dõi metric

Các metric hữu ích sau deploy:

| Nhóm | Metric |
|---|---|
| Availability | Tỷ lệ request thành công, 5xx, readiness |
| Performance | Latency p50/p95/p99, throughput |
| View rendering | Lỗi render template, thời gian render, missing attribute |
| Static assets | 404, cache hit rate, CDN origin error |
| Database | Connection pool, query latency, lock wait, migration duration |
| Business | Tỷ lệ hoàn tất đăng ký, thanh toán hoặc thao tác chính |
| Rollout | Số instance theo version, tỷ lệ traffic theo release |

Đặc biệt, hãy phân nhóm theo application version và template version để nhận diện lỗi chỉ xuất hiện trên một tổ hợp.

### Theo dõi log và trace

Khi request lỗi, log và trace nên giúp xác định:

- Request đi vào instance nào.
- Instance chạy release nào.
- Template version nào được dùng.
- Dependency nào chậm hoặc thất bại.
- Lỗi phát sinh ở Controller, application service, repository hay View rendering.
- Request có được xử lý bởi phiên bản khác sau redirect hay không.

Không đưa dữ liệu nhạy cảm của Model vào trace attribute. Chỉ ghi ID nội bộ hoặc metadata đã được đánh giá an toàn.

### Smoke test sau deploy

Sau khi chuyển traffic, chạy một số luồng kiểm tra đại diện:

- Mở trang công khai.
- Đăng nhập bằng tài khoản test.
- Xem trang có dữ liệu.
- Gửi form hợp lệ.
- Gửi form không hợp lệ và xác nhận lỗi hiển thị.
- Kiểm tra static asset được tải.
- Kiểm tra endpoint cần quyền và endpoint bị từ chối.
- Kiểm tra health/readiness và release version.

Smoke test không thay thế test đầy đủ, nhưng giúp phát hiện lỗi tích hợp giữa các thành phần trong môi trường thực.

## 16. Thay đổi template có tác động bảo mật

View template là một phần của bề mặt bảo mật. Một thay đổi nhỏ có thể làm lộ dữ liệu hoặc phá cơ chế bảo vệ.

### Output escaping

Template phải escape nội dung không tin cậy theo đúng ngữ cảnh HTML, attribute, URL hoặc JavaScript. Không dùng chế độ render raw HTML cho nội dung người dùng nếu chưa sanitize theo chính sách.

Test template nên đưa chuỗi chứa ký tự HTML đặc biệt và xác nhận nó được hiển thị như văn bản, không trở thành markup thực thi.

### CSRF token

Các form thay đổi trạng thái cần tiếp tục gửi CSRF token. Khi thay template form, hãy xác nhận hidden field hoặc cơ chế tự động tích hợp Spring Security vẫn hoạt động.

### Authorization trong View

Ẩn nút hoặc menu theo quyền có thể cải thiện trải nghiệm nhưng không thay thế authorization ở server. Khi thay template, test cần xác nhận giao diện chỉ hiển thị hành động phù hợp, đồng thời endpoint vẫn từ chối request trái phép.

### Không đưa secret vào template

Không nhúng API key, session secret hoặc dữ liệu xác thực vào JavaScript/HTML. Những giá trị được render vào browser có thể bị người dùng xem hoặc lấy qua developer tools.

## 17. Ví dụ quy trình release cho một thay đổi MVC

Giả sử release thêm nút hủy đăng ký và hiển thị trạng thái mới.

**Thay đổi cần chuẩn bị:**

- Application service hỗ trợ use case cancel.
- Controller cung cấp endpoint POST và kiểm tra quyền.
- View Model có trạng thái và cờ canCancel.
- Thymeleaf template hiển thị nút nếu được phép.
- Form gửi CSRF token.
- CSS có style cho trạng thái đã hủy.
- Database lưu trạng thái mới nếu schema cần thay đổi.
- Metric ghi nhận số lần hủy và tỷ lệ thất bại.

**Thứ tự triển khai an toàn:**

1. Migration mở rộng thêm giá trị hoặc cột cần thiết theo cách code cũ vẫn đọc được.
2. Deploy backend có endpoint mới nhưng chưa bật nút trên giao diện.
3. Deploy template và asset mới trong cùng artifact hoặc package có version rõ.
4. Chạy smoke test trên một phần traffic hoặc staging.
5. Bật feature flag cho nhóm nhỏ.
6. Theo dõi authorization failures, CSRF errors, render failures và business metrics.
7. Mở rộng rollout khi các chỉ số ổn định.
8. Sau khi mọi instance và client đã chuyển, mới cân nhắc loại bỏ code tương thích cũ trong release sau.

Nếu template được đóng gói cùng JAR, bước deploy code và template có thể là một lần phát hành artifact. Nếu template được quản lý riêng, manifest và version compatibility phải xác định chính xác cặp backend/template được phép chạy.

## 18. Các sai lầm thường gặp

### Sửa trực tiếp template trên một máy chủ

Các instance khác vẫn giữ template cũ. Load balancer khiến người dùng nhận giao diện không nhất quán. Hãy đưa template vào artifact hoặc hệ thống quản lý version tập trung.

### Build lại artifact cho từng môi trường

Nội dung có thể khác nhau giữa staging và production. Hãy build một lần, promote cùng digest và inject cấu hình theo môi trường.

### Xóa asset cũ ngay sau deploy

Tab trình duyệt cũ vẫn có thể tham chiếu asset đó. Dùng fingerprint và giữ asset cũ theo thời hạn phù hợp.

### Deploy code mới trước khi có migration

Instance mới có thể truy vấn cột chưa tồn tại. Với rolling deploy, cần migration mở rộng tương thích trước code.

### Xóa cột cũ cùng release đổi code

Instance cũ vẫn có thể đọc cột đó. Dùng expand-and-contract qua nhiều release.

### Giả định tất cả request đi vào phiên bản mới

Trong rolling/canary, phiên bản cũ vẫn nhận traffic. Hãy kiểm thử tương thích giữa form cũ và backend mới, cũng như giữa hai phiên bản đang cùng chạy.

### Chỉ kiểm tra process đã khởi động

Process có thể sống nhưng template render lỗi hoặc endpoint nghiệp vụ không hoạt động. Dùng readiness, smoke test và business metric.

### Rollback code mà quên template và asset

HTML, CSS, JavaScript hoặc template bên ngoài có thể vẫn ở phiên bản mới. Release manifest cần bao gồm mọi thành phần liên quan.

### Không quan sát theo release

Metric tổng thể có thể che lỗi chỉ xảy ra trên phiên bản mới. Gắn release ID và template version vào log/metric để so sánh.

## 19. Quy trình triển khai thay đổi code và khuôn mẫu

Một quy trình có thể áp dụng cho mỗi release:

1. Xác định phạm vi thay đổi: Controller, Model, service, template, asset, config và schema.
2. Liệt kê hợp đồng giữa View Model, form field và endpoint.
3. Đánh giá tương thích giữa phiên bản cũ và mới trong thời gian rollout.
4. Viết unit, MVC, template rendering, security và integration test.
5. Build artifact bất biến cùng asset fingerprint và release manifest.
6. Chạy database migration theo chiến lược expand-and-contract.
7. Đưa asset mới lên nơi phân phối trước khi HTML mới tham chiếu.
8. Deploy theo rolling, blue-green hoặc canary.
9. Chỉ đưa instance vào traffic khi readiness đạt.
10. Theo dõi lỗi render, 4xx/5xx, latency, asset 404 và business metric theo release.
11. Xác nhận smoke test và các luồng nghiệp vụ chính.
12. Hoàn tất rollout, hoặc thực hiện rollback/forward-fix theo kế hoạch.
13. Dọn feature flag, code tương thích và asset cũ sau khi hết thời gian chuyển tiếp.

## 20. Checklist trước và sau triển khai

### Trước triển khai

- Artifact có version/digest bất biến.
- Code và View template đã được kiểm thử cùng nhau.
- Asset mới có fingerprint và manifest rõ.
- Migration tương thích với code đang chạy.
- Runtime config đã sẵn sàng và secret không nằm trong artifact.
- Session, cache và template version tương thích khi nhiều phiên bản cùng tồn tại.
- Có health check, readiness và graceful shutdown.
- Có tiêu chí dừng rollout và rollback.
- Có release ID để phân tích log, metric và trace.

### Sau triển khai

- Tất cả instance đã chạy đúng version dự kiến.
- Template version và asset manifest khớp release.
- Không có lỗi render hoặc missing model attribute bất thường.
- Static asset không có tỷ lệ 404 tăng.
- Tỷ lệ 4xx/5xx và latency nằm trong ngưỡng.
- Database migration hoàn tất và không có lock bất thường.
- Người dùng hoàn thành được các use case chính.
- CSRF, authorization và output escaping vẫn hoạt động.
- Cache không trả dữ liệu hoặc template của phiên bản khác.
- Có thể xác định chính xác release đang phục vụ từng request.

## Kết luận

Triển khai thay đổi mã và khuôn mẫu đồng bộ là bảo đảm Controller, Model, View template, static assets, cấu hình và database cùng tuân theo những hợp đồng tương thích. Artifact bất biến, version rõ ràng và kiểm thử rendering giúp giảm sai lệch giữa môi trường. Rolling, blue-green và canary cho phép chuyển phiên bản có kiểm soát, nhưng đòi hỏi code, template, session và schema vẫn tương thích trong giai đoạn chuyển tiếp.

Sau deploy, health check, smoke test, log, metric và trace theo release giúp xác nhận hệ thống thực sự phục vụ đúng phiên bản và hoàn thành use case. Kế hoạch rollback cần xét cả code, template, asset và dữ liệu đã thay đổi. Khi quản lý toàn bộ vòng đời release như một quy trình có thể quan sát và khôi phục, ứng dụng MVC sẽ giảm lỗi triển khai và duy trì trải nghiệm nhất quán cho người dùng.
