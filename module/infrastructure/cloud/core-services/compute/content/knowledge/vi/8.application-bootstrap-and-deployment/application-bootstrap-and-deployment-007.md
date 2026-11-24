# So sánh cập nhật tại chỗ với thay máy theo mô hình immutable

Khi triển khai phiên bản mới của ứng dụng trên đám mây, đội vận hành thường chọn một trong hai cách: cập nhật phần mềm ngay trên các máy đang chạy hoặc tạo các máy mới từ một cấu hình đã được chuẩn bị, chuyển lưu lượng sang máy mới rồi loại bỏ máy cũ. Cách thứ nhất thường được gọi là *cập nhật tại chỗ* (in-place update); cách thứ hai là *triển khai hạ tầng bất biến* (immutable infrastructure).

Hai cách đều có thể vận hành tốt nếu phù hợp với ứng dụng và quy trình phát hành. Cập nhật tại chỗ tận dụng tài nguyên hiện có và có thể đơn giản với hệ thống nhỏ. Mô hình immutable tạo ra các đơn vị triển khai có phiên bản rõ ràng, dễ kiểm thử và thay thế, giúp giảm sai khác giữa các môi trường. Lựa chọn cần dựa trên yêu cầu sẵn sàng, khả năng rollback, trạng thái dữ liệu, tốc độ phát hành, chi phí và năng lực tự động hóa.

Bài học này đặt hai cách tiếp cận cạnh nhau trong bối cảnh triển khai năng lực tính toán trên đám mây, từ máy ảo đến container và serverless. Sau bài học, bạn có thể:

- Giải thích cách hoạt động và các rủi ro của cập nhật tại chỗ và thay máy theo mô hình immutable.
- So sánh tác động của mỗi cách đến độ sẵn sàng, khả năng khôi phục, bảo mật, chi phí và vận hành.
- Chọn chiến lược phát hành như recreate, rolling, blue-green hoặc canary phù hợp với yêu cầu dịch vụ.
- Thiết kế quy trình tạo artifact có phiên bản, kiểm tra sức khỏe, chuyển lưu lượng và rollback.
- Xử lý cấu hình, bí mật và dữ liệu bền vững khi thay thế máy hoặc phiên bản ứng dụng.

## 1. Hai cách triển khai khác nhau ở đâu?

### Cập nhật tại chỗ (in-place update)

Với cập nhật tại chỗ, hệ thống giữ lại máy ảo, máy chủ hoặc container đang tồn tại rồi thay đổi nội dung bên trong. Ví dụ, quy trình có thể kết nối tới máy ảo, tải gói phần mềm mới, thay file ứng dụng, cập nhật thư viện, sửa cấu hình và khởi động lại dịch vụ.

Một quy trình cập nhật tại chỗ trên máy ảo thường gồm:

1. Chọn máy cần cập nhật và xác nhận máy vẫn đáp ứng điều kiện vận hành.
2. Sao lưu hoặc ghi nhận phiên bản hiện tại.
3. Tải gói phát hành mới lên máy.
4. Cài đặt hoặc thay thế file, cập nhật cấu hình và quyền truy cập.
5. Khởi động lại tiến trình hoặc dịch vụ.
6. Kiểm tra health check, log và khả năng phục vụ yêu cầu.
7. Tiếp tục với các máy còn lại hoặc khôi phục phiên bản trước nếu có lỗi.

Ưu điểm là không cần tạo toàn bộ nhóm máy mới. Cách làm này có thể phù hợp với máy đơn lẻ, hệ thống cũ chưa được đóng gói, ứng dụng có quy trình cập nhật đặc biệt hoặc môi trường phát triển. Với hệ thống nhỏ, nó cũng có thể là bước đầu đơn giản để tự động hóa phát hành.

Tuy nhiên, mỗi lần cập nhật làm thay đổi trạng thái của máy hiện có. Nếu một lần phát hành cài thêm gói hệ thống, lần khác sửa file cấu hình thủ công, các máy có thể dần khác nhau. Sai khác tích lũy này được gọi là *configuration drift*. Một máy có thể chạy đúng nhờ một thao tác thủ công trước đây nhưng không thể tái tạo chính xác khi cần thay thế.

Việc cập nhật cũng có thể thất bại giữa chừng. Chẳng hạn, file mới đã được chép lên nhưng dịch vụ chưa khởi động được; một thư viện đã nâng cấp nhưng một tiến trình khác vẫn cần phiên bản cũ. Rollback đòi hỏi biết chính xác những gì đã thay đổi và có cách khôi phục cả gói phần mềm lẫn cấu hình tương ứng.

### Thay máy theo mô hình immutable

Với mô hình immutable, nhóm vận hành không sửa trực tiếp một máy đang phục vụ để biến nó thành phiên bản mới. Thay vào đó, nhóm tạo một artifact hoặc image có phiên bản, dùng nó để khởi tạo đơn vị tính toán mới, kiểm tra đơn vị mới rồi chuyển lưu lượng sang đó. Sau khi đơn vị mới hoạt động ổn định, nhóm đưa máy hoặc phiên bản cũ ra khỏi dịch vụ.

Artifact có thể là:

- Machine image đã cài hệ điều hành, runtime và thành phần ứng dụng cần thiết.
- Container image được gắn tag bất biến hoặc tham chiếu bằng digest.
- Gói ứng dụng đã build, được triển khai trên một nhóm máy mới có cấu hình được quản lý.
- Phiên bản hàm hoặc revision mới trong một nền tảng serverless.

Quy trình điển hình:

1. Build artifact từ mã nguồn và dependency đã khóa phiên bản.
2. Quét lỗ hổng, chạy kiểm thử và lưu artifact vào kho có quản lý phiên bản.
3. Tạo máy, container hoặc revision mới từ đúng artifact đó.
4. Nạp cấu hình môi trường và bí mật từ nguồn quản lý bên ngoài artifact.
5. Chạy kiểm tra khởi động, readiness và smoke test.
6. Chuyển một phần hoặc toàn bộ lưu lượng sang phiên bản mới.
7. Theo dõi chỉ số và log; nếu đạt yêu cầu thì drain và loại bỏ phiên bản cũ.
8. Nếu có lỗi, chuyển lưu lượng về phiên bản đã biết là tốt và điều tra phiên bản mới.

Máy đang chạy được xem như một đơn vị có vòng đời rõ ràng. Khi cần cập nhật hệ điều hành hoặc thư viện nền, nhóm tạo image mới và thay máy theo cùng quy trình. Điều này giúp trạng thái triển khai dễ tái tạo và kiểm toán hơn.

Immutable không có nghĩa là không bao giờ thay đổi hệ thống. Mã nguồn, image, cấu hình khai báo và hạ tầng vẫn được cập nhật qua các phiên bản. Điểm cốt lõi là mỗi đơn vị đã được đưa vào phục vụ không bị chỉnh sửa tùy tiện để trở thành một trạng thái khó tái tạo; thay đổi được đóng gói thành phiên bản mới rồi thay thế có kiểm soát.

## 2. So sánh theo tiêu chí vận hành

| Tiêu chí | Cập nhật tại chỗ | Thay máy theo mô hình immutable |
|---|---|---|
| Cách thay đổi | Sửa phần mềm hoặc cấu hình trên máy hiện có | Tạo đơn vị mới từ artifact/image đã phiên bản hóa |
| Tài nguyên trong lúc phát hành | Thường tận dụng máy đang có | Có thể cần chạy song song máy cũ và máy mới |
| Tái tạo môi trường | Phụ thuộc mức độ ghi nhận thao tác và trạng thái máy | Dễ hơn nếu build và cấu hình được tự động hóa |
| Configuration drift | Dễ tích lũy qua nhiều lần sửa | Giảm khi máy mới luôn được tạo từ nguồn chuẩn |
| Rủi ro phát hành | Máy có thể ở trạng thái nửa cập nhật hoặc các máy lệch phiên bản | Có rủi ro ở artifact mới và quá trình chuyển lưu lượng |
| Rollback | Có thể phải hoàn tác nhiều thay đổi trên máy | Có thể chuyển lại phiên bản hoặc nhóm máy cũ nếu vẫn được giữ |
| Thời gian triển khai | Có thể nhanh với thay đổi nhỏ, nhưng phụ thuộc từng máy | Cần thời gian build và khởi tạo, có thể phát hành song song |
| Mở rộng ngang | Phải bảo đảm máy mới cũng được cập nhật đúng | Có thể tạo thêm máy từ cùng artifact đã kiểm thử |
| Bản vá hệ điều hành | Thường cập nhật trực tiếp từng máy | Build image mới rồi thay dần các máy |
| Yêu cầu tự động hóa | Có thể bắt đầu bằng script; khó kiểm soát khi quy mô tăng | Cần pipeline build, lưu artifact, cấp phát và điều phối |
| Phù hợp với | Hệ thống nhỏ, cũ, ít thay đổi hoặc cần cập nhật có kiểm soát trên máy đặc thù | Dịch vụ phân tán, autoscaling, phát hành thường xuyên và cần tái tạo nhất quán |

Không có cách nào tự động bảo đảm không downtime. Một lần thay máy vẫn có thể gây gián đoạn nếu nhóm dừng máy cũ trước khi máy mới sẵn sàng, nếu load balancer chưa cập nhật hoặc nếu ứng dụng không xử lý kết nối đang mở. Ngược lại, cập nhật tại chỗ có thể giữ dịch vụ liên tục nếu cập nhật tuần tự và luôn duy trì đủ máy khỏe mạnh. Điều quyết định là chiến lược rollout, kiến trúc ứng dụng và cách kiểm tra sức khỏe.

## 3. Các chiến lược phát hành thường dùng

In-place hay immutable mô tả cách thay đổi đơn vị triển khai. Recreate, rolling, blue-green và canary mô tả cách đưa phiên bản mới vào phục vụ. Các chiến lược rollout này thường được dùng cùng mô hình immutable, nhưng một số cũng có thể áp dụng cho cập nhật tại chỗ.

### Recreate

Recreate dừng các đơn vị cũ rồi tạo đơn vị mới. Cách này đơn giản, ít tốn tài nguyên chạy song song nhưng có thể gây downtime trong thời gian khởi tạo và kiểm tra. Chỉ nên dùng khi dịch vụ chấp nhận gián đoạn, có cửa sổ bảo trì hoặc đã có cơ chế dự phòng khác.

### Rolling update

Rolling update thay từng nhóm nhỏ máy hoặc container. Hệ thống giữ một phần phiên bản cũ trong lúc phiên bản mới khởi động và vượt qua kiểm tra. Khi nhóm mới khỏe mạnh, nhóm tiếp theo mới được thay.

Ví dụ, một dịch vụ có 6 instance có thể thay 2 instance mỗi đợt, đồng thời duy trì ít nhất 4 instance khỏe mạnh. Con số thực tế phụ thuộc tải, thời gian khởi động và năng lực dự phòng. Cần đặt giới hạn số instance tối đa/tối thiểu trong quá trình rollout để không làm thiếu năng lực hoặc vượt ngân sách.

Rolling update tiết kiệm tài nguyên hơn blue-green nhưng trong một khoảng thời gian có hai phiên bản cùng phục vụ. API, schema dữ liệu và giao thức trao đổi giữa các phiên bản phải tương thích trong giai đoạn này.

### Blue-green deployment

Blue-green duy trì hai nhóm môi trường: nhóm đang phục vụ (blue) và nhóm mới (green). Nhóm green được tạo và kiểm thử riêng. Khi sẵn sàng, bộ định tuyến hoặc load balancer chuyển lưu lượng từ blue sang green. Nhóm blue có thể được giữ lại trong một khoảng thời gian để rollback nhanh.

Sơ đồ chuyển đổi:

~~~mermaid
flowchart LR
    U["Người dùng"] --> R["Load balancer / router"]
    R --> B["Blue: phiên bản đang phục vụ"]
    R -. "sau khi xác nhận" .-> G["Green: phiên bản mới"]
    B --> D[("Dịch vụ dữ liệu dùng chung")]
    G --> D
~~~

Blue-green tạo điểm chuyển đổi rõ ràng và thuận tiện rollback ở tầng định tuyến. Đổi lại, cần đủ tài nguyên cho hai môi trường trong thời gian phát hành. Cần đặc biệt cẩn trọng với dữ liệu dùng chung: rollback ứng dụng không thể tự động đảo ngược một migration cơ sở dữ liệu phá vỡ tương thích.

### Canary deployment

Canary đưa phiên bản mới tới một phần nhỏ lưu lượng hoặc một nhóm người dùng trước. Nhóm vận hành so sánh lỗi, độ trễ, thông lượng và các chỉ số nghiệp vụ giữa phiên bản mới và phiên bản hiện tại. Nếu kết quả đạt ngưỡng, tỷ lệ lưu lượng được tăng dần; nếu xấu đi, lưu lượng được đưa trở lại phiên bản ổn định.

Canary giúp phát hiện vấn đề chỉ xuất hiện dưới tải thực hoặc với một nhóm dữ liệu nhất định. Cần có cách chia lưu lượng nhất quán, đủ mẫu để đánh giá và ngưỡng tự động dừng rollout. Một tỷ lệ nhỏ lưu lượng không có ý nghĩa nếu chỉ có vài yêu cầu hoặc không đại diện cho nhóm người dùng thật.

| Chiến lược | Mức độ chuyển đổi | Nhu cầu tài nguyên song song | Điểm cần chú ý |
|---|---|---|---|
| Recreate | Thay toàn bộ sau khi dừng bản cũ | Thấp | Có thể downtime |
| Rolling | Thay từng nhóm | Vừa | Hai phiên bản cùng tồn tại trong lúc chuyển đổi |
| Blue-green | Chuyển giữa hai môi trường | Cao, thường gần gấp đôi ở tầng compute | Cần quản lý route và dữ liệu dùng chung |
| Canary | Tăng dần tỷ lệ lưu lượng | Tùy cách triển khai | Cần chỉ số và tiêu chí dừng đáng tin cậy |

## 4. Artifact, image và cấu hình phải có phiên bản

Mô hình immutable chỉ có thể tái tạo khi biết chính xác thứ gì đã tạo ra một máy hoặc revision. Vì vậy, artifact cần được quản lý như một sản phẩm phát hành.

### Build một lần, triển khai nhiều môi trường

Pipeline nên build và kiểm thử artifact một lần, sau đó đưa cùng artifact đã được xác minh qua môi trường thử nghiệm, staging và production. Nếu build lại riêng cho production, dependency hoặc nội dung image có thể khác với thứ đã được kiểm thử.

Với container, tag như latest không xác định duy nhất nội dung image vì tag có thể được di chuyển sang image khác. Trong triển khai cần tham chiếu phiên bản bất biến hoặc digest, ví dụ:

~~~text
registry.example.com/orders-api@sha256:abc123...
~~~

Digest trong ví dụ chỉ minh họa định dạng tham chiếu; cần dùng digest thực do registry trả về. Với machine image, hãy lưu image ID hoặc phiên bản image cùng metadata build. Với gói ứng dụng, lưu checksum và phiên bản phát hành.

### Tách cấu hình khỏi artifact

Artifact nên chứa ứng dụng và dependency cần thiết. Các giá trị thay đổi theo môi trường như URL dịch vụ, tên cụm, feature flag, giới hạn kết nối và thông tin xác thực được cung cấp lúc chạy từ hệ thống cấu hình hoặc secret manager.

Không đưa mật khẩu, token, private key hay thông tin xác thực vào image, repository hoặc log build. Quyền đọc bí mật cần cấp theo nguyên tắc tối thiểu cho workload identity hoặc vai trò của máy. Khi thay phiên bản, đơn vị mới nhận đúng cấu hình và quyền của môi trường đích.

Tách cấu hình không đồng nghĩa để cấu hình thay đổi không kiểm soát. Cần quản lý phiên bản, người phê duyệt và lịch sử thay đổi cho cấu hình quan trọng, đồng thời xác định cách đồng bộ giữa các instance.

### Tạo image có thể tái tạo

Một image máy ảo hoặc container nên được tạo từ định nghĩa có thể kiểm tra trong mã nguồn. Ví dụ Dockerfile tối giản:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/orders-api.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ này minh họa cách đóng gói một ứng dụng Java vào container, dùng runtime cụ thể và chạy bằng người dùng không phải root. Trong hệ thống thực tế, cần cố định phiên bản image nền hoặc digest, quét lỗ hổng, kiểm soát dependency, không copy file bí mật vào image và bảo đảm ứng dụng ghi dữ liệu bền vững ra dịch vụ lưu trữ phù hợp. EXPOSE chỉ mô tả cổng dự kiến của container, không tự cấu hình firewall hay mở cổng trên đám mây.

## 5. Dữ liệu và trạng thái khi thay máy

Một máy có thể được thay thế dễ dàng chỉ khi dữ liệu cần giữ lại không bị khóa trong ổ đĩa tạm của máy đó. Trước khi áp dụng immutable, hãy phân loại trạng thái:

- **Trạng thái tạm:** cache cục bộ, file tạm, dữ liệu có thể tạo lại. Có thể mất khi thay máy nếu ứng dụng được thiết kế đúng.
- **Trạng thái phiên:** thông tin đăng nhập hoặc giỏ hàng đang hoạt động. Nên lưu ở kho phiên dùng chung hoặc dùng token phù hợp thay vì phụ thuộc vào bộ nhớ của một instance.
- **Dữ liệu nghiệp vụ bền vững:** đơn hàng, tài khoản, giao dịch, file người dùng. Cần đặt trong cơ sở dữ liệu hoặc object storage có vòng đời độc lập với máy ứng dụng.
- **Dữ liệu cục bộ cần giữ:** nếu ứng dụng có yêu cầu đặc biệt về volume, phải có cơ chế attach/detach, snapshot, backup và kiểm tra tính nhất quán trước khi thay máy.

Với nhóm máy stateless, instance có thể được tạo hoặc hủy theo nhu cầu. Load balancer phân phối yêu cầu tới các instance khỏe mạnh; dữ liệu quan trọng được lưu ở hệ thống bên ngoài. Thiết kế này hỗ trợ autoscaling và thay thế instance dễ hơn.

### Migration cơ sở dữ liệu cần tương thích ngược

Trong rolling hoặc blue-green, phiên bản ứng dụng cũ và mới có thể cùng chạy. Vì vậy, migration nên theo hướng *expand-contract*:

1. **Expand:** thêm cột, bảng hoặc API mới theo cách không làm phiên bản cũ lỗi.
2. Triển khai ứng dụng mới có thể đọc/ghi theo cấu trúc mới, trong khi vẫn hỗ trợ cấu trúc cũ trong giai đoạn chuyển tiếp.
3. Chuyển đổi hoặc backfill dữ liệu, kiểm tra tính đầy đủ và nhất quán.
4. **Contract:** chỉ xóa cột, bảng hoặc đường tương thích cũ sau khi xác nhận không còn phiên bản nào phụ thuộc.

Không nên gộp một migration phá vỡ tương thích vào cùng thời điểm chuyển traffic nếu chưa có kế hoạch khôi phục dữ liệu. Rollback binary không đảo ngược dữ liệu đã ghi hoặc schema đã thay đổi. Backup, restore test và kế hoạch phục hồi dữ liệu phải được thiết kế riêng.

## 6. Kiểm tra sức khỏe và chuyển lưu lượng an toàn

Máy mới khởi động thành công chưa chắc đã sẵn sàng phục vụ. Nên phân biệt:

- **Startup check:** ứng dụng đã hoàn tất khởi tạo, nạp cấu hình và kết nối thành phần cần thiết hay chưa.
- **Readiness check:** instance có thể nhận yêu cầu mới hay không. Instance chưa ready không nên nhận traffic.
- **Liveness check:** tiến trình có còn hoạt động và có cần khởi động lại hay không. Liveness không nên thất bại chỉ vì một dependency bên ngoài tạm thời chậm.
- **Smoke test:** một số yêu cầu đại diện xác nhận các chức năng quan trọng hoạt động sau khi triển khai.

Khi loại máy cũ khỏi load balancer, hãy ngừng nhận yêu cầu mới trước, chờ hoặc chuyển tiếp các kết nối đang xử lý, rồi mới dừng tiến trình. Cách này thường được gọi là *connection draining* hoặc graceful shutdown. Ứng dụng nên xử lý tín hiệu dừng, hoàn tất giao dịch đang chạy trong thời gian cho phép và đóng tài nguyên đúng cách.

Một rollout an toàn cần ngưỡng rõ ràng, ví dụ: tỷ lệ lỗi không vượt ngưỡng, p95 latency không tăng quá mức cho phép, số instance ready luôn đủ phục vụ tải và các kiểm tra nghiệp vụ quan trọng đều thành công. Ngưỡng phải được xác định theo SLO của dịch vụ thay vì đặt tùy ý.

## 7. Áp dụng trên máy ảo, container và serverless

| Nền tảng | Cập nhật tại chỗ | Cách làm theo hướng immutable |
|---|---|---|
| Máy ảo | Kết nối vào VM, cài gói mới, sửa file và restart dịch vụ | Build machine image mới, tạo VM mới, kiểm tra, chuyển traffic qua load balancer rồi loại VM cũ |
| Container | Exec vào container đang chạy hoặc thay file trong writable layer | Build image mới, triển khai task/pod mới từ digest đã khóa, chờ readiness rồi thay replica cũ |
| Serverless | Sửa cấu hình hoặc mã của deployment đang hoạt động theo cơ chế nền tảng | Publish version/revision mới, kiểm thử và chuyển alias hoặc tỷ lệ traffic sang revision đó |

Với máy ảo, immutable thường đem lại lợi ích lớn khi có image pipeline và nhóm instance được quản lý. Nếu phải đăng nhập và sửa từng VM, khả năng tái tạo và rollback sẽ giảm.

Với container, image bất biến là cách đóng gói tự nhiên: nội dung image không đổi sau khi build. Khi ứng dụng cần phiên bản mới, tạo container mới từ image mới. Không nên dùng thao tác sửa trực tiếp bên trong container đang chạy như một quy trình phát hành chính thức vì thay đổi đó không có trong image và sẽ mất khi container được tạo lại.

Với serverless, nhà cung cấp quản lý phần lớn máy chủ nền. Nhóm phát triển vẫn có thể áp dụng cùng nguyên tắc bằng cách tạo version hoặc revision mới, gắn cấu hình rõ ràng và chuyển traffic có kiểm soát. Việc cập nhật nền tảng do nhà cung cấp thực hiện cần được xem xét theo chính sách runtime, lịch deprecation và mức độ tương thích.

## 8. Quy trình CI/CD tham khảo

Một pipeline triển khai immutable có thể chia thành các giai đoạn sau:

~~~mermaid
flowchart TD
    A["Commit mã nguồn"] --> B["Build artifact có phiên bản"]
    B --> C["Unit test, integration test, quét bảo mật"]
    C --> D["Đẩy artifact vào registry"]
    D --> E["Tạo nhóm compute mới"]
    E --> F["Startup, readiness và smoke test"]
    F --> G{"Đạt ngưỡng phát hành?"}
    G -- "Không" --> H["Dừng rollout và giữ phiên bản ổn định"]
    G -- "Có" --> I["Canary hoặc chuyển traffic"]
    I --> J{"Chỉ số sau chuyển đổi tốt?"}
    J -- "Không" --> K["Rollback route về phiên bản cũ"]
    J -- "Có" --> L["Drain và loại nhóm cũ"]
~~~

Pipeline cần lưu lại mã commit, phiên bản artifact, digest/image ID, cấu hình triển khai, kết quả kiểm thử và người/phê duyệt phát hành. Nhờ đó, khi có sự cố có thể xác định chính xác phiên bản nào đang chạy và tái tạo môi trường cần điều tra.

Một bộ bước phát hành tham khảo:

~~~text
1. Build artifact từ commit đã chọn.
2. Kiểm thử và quét bảo mật.
3. Gắn phiên bản bất biến; ghi lại checksum hoặc digest.
4. Tạo nhóm compute mới từ artifact đó.
5. Nạp cấu hình và secret qua cơ chế runtime.
6. Chờ readiness và chạy smoke test.
7. Chuyển một phần traffic; quan sát lỗi, độ trễ và thông lượng.
8. Tăng dần traffic nếu đạt ngưỡng.
9. Drain và xóa compute cũ sau thời gian quan sát.
10. Lưu trạng thái phát hành và kết quả vào hệ thống theo dõi.
~~~

Trong thực tế, các bước được thực hiện bằng công cụ CI/CD, image builder, hệ thống quản lý cấu hình, bộ điều phối container, load balancer hoặc dịch vụ serverless của nền tảng. Tên công cụ có thể khác nhau nhưng các điều kiện kiểm soát vẫn tương tự.

## 9. Rollback và phục hồi

Rollback phải được chuẩn bị trước khi phát hành. Với immutable, nếu phiên bản cũ vẫn tồn tại và dữ liệu còn tương thích, có thể chuyển traffic trở lại phiên bản cũ hoặc triển khai lại artifact đã biết là tốt. Đây thường là thao tác nhanh và dễ xác định hơn việc đảo ngược nhiều thay đổi trên từng máy.

Một kế hoạch rollback nên trả lời:

- Phiên bản ổn định gần nhất là artifact nào? Có thể truy xuất bằng ID hoặc digest không?
- Nhóm compute cũ được giữ trong bao lâu? Khi nào được phép xóa?
- Ai hoặc điều kiện nào có quyền dừng rollout?
- Có thể chuyển traffic lại trong bao lâu?
- Schema và dữ liệu có tương thích với phiên bản cũ không?
- Nếu lỗi liên quan đến cấu hình hoặc bí mật, cách phục hồi và thu hồi quyền là gì?
- Backup có thể khôi phục được không và thời gian khôi phục đã được kiểm thử chưa?

Rollback ứng dụng và rollback dữ liệu là hai việc khác nhau. Khi phiên bản mới đã ghi dữ liệu theo định dạng mới, quay về binary cũ có thể khiến ứng dụng không đọc được dữ liệu. Vì vậy, hãy ưu tiên migration tương thích ngược và chuẩn bị quy trình sửa dữ liệu có kiểm soát.

Không nên xóa ngay nhóm cũ sau khi chuyển traffic nếu dịch vụ quan trọng và chi phí cho giai đoạn giữ dự phòng chấp nhận được. Thời gian giữ phụ thuộc thời gian phát hiện lỗi, đặc điểm tải và yêu cầu phục hồi. Sau thời gian quan sát, có thể kết thúc tài nguyên cũ để tránh chi phí không cần thiết.

## 10. Bảo mật và quản trị cấu hình

Immutable giúp kiểm soát nguồn gốc của phần mềm và image, nhưng không tự động làm hệ thống an toàn. Cần kết hợp các kiểm soát sau:

- Dùng image nền được duy trì, cập nhật bản vá và tạo image mới theo lịch hoặc khi có lỗ hổng nghiêm trọng.
- Quét image, dependency và artifact; ký hoặc xác minh nguồn gốc artifact nếu quy trình yêu cầu.
- Chạy ứng dụng với quyền tối thiểu, tránh root khi không cần và cấp danh tính workload riêng.
- Lấy secret lúc chạy từ secret manager, giới hạn phạm vi và luân chuyển thông tin xác thực.
- Ghi nhận ai đã tạo, phê duyệt và triển khai artifact; giữ audit log cho thay đổi cấu hình.
- Hạn chế truy cập quản trị trực tiếp vào máy production; nếu cần thao tác khẩn cấp, ghi nhận thay đổi và đưa nội dung sửa chữa trở lại image hoặc mã cấu hình chuẩn.
- Theo dõi tuổi image và phiên bản runtime để không bỏ sót các máy cũ đang phục vụ.

Với cập nhật tại chỗ, cần thêm kiểm soát về thứ tự thao tác, quyền truy cập shell, backup trước thay đổi và ghi nhận trạng thái từng máy. Nếu có máy không cập nhật thành công, phải đưa máy đó ra khỏi pool hoặc có biện pháp ngăn nó phục vụ với phiên bản lệch.

## 11. Chi phí và năng lực vận hành

Immutable có thể cần chạy đồng thời nhóm cũ và nhóm mới trong thời gian phát hành. Do đó, chi phí compute tạm thời tăng lên. Blue-green thường cần mức dự phòng lớn hơn rolling; canary có thể bắt đầu với một nhóm nhỏ. Ngoài compute, còn có chi phí lưu image, pipeline build, lưu log và công cụ điều phối.

Cập nhật tại chỗ có thể dùng ít tài nguyên hơn trong lúc phát hành, nhưng chi phí ẩn có thể xuất hiện từ sự cố khó tái tạo, thời gian xử lý drift, downtime, rollback thủ công và kiểm tra từng máy.

Để so sánh công bằng, hãy đo:

- Chi phí tài nguyên trong một lần phát hành, gồm thời gian chạy song song.
- Thời gian từ lúc bắt đầu triển khai đến khi phiên bản mới ổn định.
- Số lỗi phát hành, tỷ lệ rollback và thời gian phục hồi trung bình.
- Thời gian vận hành cần thiết để xử lý khác biệt giữa các máy.
- Mức sử dụng CPU, bộ nhớ, mạng và lưu trữ trong giai đoạn rollout.
- Khả năng mở rộng và thu nhỏ tự động sau khi hoàn tất phát hành.

Với dịch vụ có nhiều instance, autoscaling và phát hành thường xuyên, chi phí tạo máy mới thường có thể dự đoán và tự động hóa. Với máy đặc thù có chi phí khởi tạo cao hoặc dữ liệu cục bộ khó di chuyển, cần đánh giá kỹ khả năng thay thế và thời gian chuyển đổi.

## 12. Chọn cách tiếp cận phù hợp

Hãy ưu tiên cập nhật tại chỗ khi hệ thống có quy mô nhỏ, máy đặc thù, tần suất thay đổi thấp, hoặc chưa thể đóng gói và tái tạo môi trường. Trong trường hợp đó, hãy tự động hóa thao tác, ghi nhận phiên bản, cập nhật tuần tự, kiểm tra sức khỏe và chuẩn bị rollback rõ ràng.

Hãy ưu tiên immutable khi ứng dụng có thể đóng gói, cần mở rộng ngang, phát hành thường xuyên, yêu cầu môi trường nhất quán hoặc cần rollback nhanh. Cách này đặc biệt hữu ích với nhóm VM được quản lý, container và serverless revision.

Có thể triển khai theo từng giai đoạn:

1. Chuẩn hóa build và quản lý artifact.
2. Tự động hóa cấu hình để máy mới có thể được tạo nhất quán.
3. Tách dữ liệu bền vững và secret khỏi máy ứng dụng.
4. Tạo một nhóm máy mới song song và kiểm tra trước khi nhận traffic.
5. Chuyển dần sang rolling hoặc blue-green; bổ sung canary cho dịch vụ có chỉ số quan sát tốt.
6. Loại bỏ thao tác sửa trực tiếp sau khi quy trình thay thế đã ổn định.

Nếu bắt buộc dùng mô hình lai, hãy xác định rõ thành phần nào được cập nhật tại chỗ và thành phần nào được thay mới. Ví dụ, một hệ thống cũ có thể tiếp tục dùng cập nhật tại chỗ cho máy điều khiển đặc thù nhưng dùng image bất biến cho nhóm web stateless. Tránh để cùng một máy lúc thì được quản lý bởi pipeline, lúc thì được sửa thủ công mà không có cơ chế đồng bộ.

## 13. Ví dụ: phát hành phiên bản mới của dịch vụ đặt hàng

Giả sử dịch vụ orders-api chạy trên 6 máy ảo sau một load balancer. Phiên bản hiện tại là v1.4.2; nhóm cần phát hành v1.5.0, bổ sung trường trạng thái xử lý đơn hàng.

**Nếu cập nhật tại chỗ**, pipeline kết nối lần lượt tới từng VM, tải gói v1.5.0, thay file ứng dụng và restart dịch vụ. Nếu VM thứ ba cập nhật lỗi, nhóm phải biết hai VM đầu đã ở phiên bản mới, VM thứ ba ở trạng thái nào và ba VM còn lại đang chạy phiên bản nào. Nếu schema cơ sở dữ liệu đã thay đổi theo cách phiên bản cũ không đọc được, rollback ứng dụng có thể thất bại.

**Nếu triển khai immutable**, nhóm build artifact v1.5.0, kiểm thử và tạo nhóm VM mới từ image đã chuẩn hóa. Nhóm mới nạp cấu hình và secret khi khởi động, kết nối tới cơ sở dữ liệu dùng chung và chạy readiness test. Sau đó, load balancer gửi một tỷ lệ nhỏ yêu cầu tới nhóm mới. Nếu tỷ lệ lỗi và p95 latency trong ngưỡng, nhóm tăng dần traffic rồi drain nhóm cũ.

Để giữ khả năng rollback, nhóm triển khai migration theo hướng expand trước: thêm trường mới theo cách phiên bản v1.4.2 vẫn hoạt động. Sau khi mọi instance đã chuyển sang v1.5.0 và dữ liệu được xác minh, nhóm mới xem xét loại bỏ đường tương thích cũ trong một lần phát hành riêng.

Trong ví dụ này, immutable làm rõ phiên bản nào đang chạy và cho phép chuyển traffic về nhóm cũ nếu lỗi. Đổi lại, nhóm cần đủ tài nguyên chạy song song, image pipeline và cách quản lý migration tương thích.

## 14. Những lỗi thường gặp

1. **Cho rằng immutable tự động không downtime:** nếu dừng máy cũ trước khi máy mới ready, dịch vụ vẫn có thể gián đoạn.
2. **Dùng tag có thể thay đổi:** cùng một tag image nhưng nội dung khác nhau làm mất khả năng tái tạo chính xác.
3. **Đưa secret vào image:** image có thể được lưu lâu hoặc chia sẻ rộng, khiến bí mật khó thu hồi.
4. **Lưu dữ liệu nghiệp vụ trên ổ đĩa tạm của instance:** thay máy có thể làm mất dữ liệu.
5. **Rollback binary nhưng quên schema:** phiên bản cũ có thể không tương thích với dữ liệu đã được ghi bởi phiên bản mới.
6. **Không giữ đủ capacity trong rolling update:** số instance ready giảm dưới mức cần thiết hoặc autoscaler không kịp bổ sung.
7. **Không có health check phù hợp:** máy mới nhận traffic trước khi hoàn tất khởi tạo hoặc máy cũ bị restart liên tục vì liveness check quá nhạy.
8. **Sửa nóng máy production nhưng không cập nhật nguồn chuẩn:** lần thay máy sau sẽ làm mất sửa chữa và tái xuất hiện lỗi.
9. **Xóa nhóm cũ quá sớm:** khi lỗi chỉ xuất hiện dưới tải thực, không còn phiên bản ổn định để chuyển traffic về.

## 15. Checklist trước một lần phát hành

- [ ] Artifact có phiên bản duy nhất, checksum hoặc digest được ghi nhận.
- [ ] Build và kiểm thử được thực hiện trên đúng artifact sẽ triển khai.
- [ ] Image nền, dependency và runtime đã được kiểm tra bảo mật.
- [ ] Cấu hình môi trường và secret được cấp từ nguồn quản lý phù hợp.
- [ ] Dữ liệu bền vững nằm ngoài vòng đời của instance hoặc có quy trình bảo vệ rõ ràng.
- [ ] Migration tương thích với các phiên bản có thể cùng chạy trong rollout.
- [ ] Có startup, readiness, liveness và smoke test phù hợp.
- [ ] Có đủ capacity cho chiến lược rollout đã chọn.
- [ ] Có ngưỡng theo dõi lỗi, độ trễ, thông lượng và điều kiện dừng tự động.
- [ ] Có phương án chuyển traffic về phiên bản ổn định.
- [ ] Có kế hoạch drain kết nối và kết thúc instance cũ.
- [ ] Có người chịu trách nhiệm, lịch sử phát hành và thời gian quan sát sau triển khai.

## 16. Bài tập vận dụng

Một dịch vụ API chạy trên 8 container, mỗi container phục vụ một phần lưu lượng. Nhóm chuẩn bị phát hành image mới có thay đổi thư viện xử lý JSON. Yêu cầu là không để số replica ready thấp hơn 6, giữ p95 latency trong SLO và có thể rollback trong vài phút.

1. Hãy đề xuất cách triển khai rolling, blue-green hoặc canary và giải thích lý do.
2. Nếu dùng rolling update, cần đặt giới hạn số container được tạo thêm và số container được dừng như thế nào để vẫn duy trì ít nhất 6 replica ready?
3. Những kiểm tra nào phải đạt trước khi một container mới nhận traffic?
4. Nếu phiên bản mới ghi thêm một trường vào cơ sở dữ liệu, cần triển khai migration theo thứ tự nào để phiên bản cũ và mới cùng hoạt động?
5. Nhóm cần giữ lại những thông tin nào để rollback đúng image và cấu hình?

Gợi ý: bắt đầu bằng yêu cầu capacity tối thiểu và thời gian rollback. Với rolling, chỉ dừng replica cũ sau khi replica mới đã ready và tổng số replica khỏe mạnh vẫn đạt yêu cầu. Với canary, chuyển một phần lưu lượng và theo dõi lỗi, độ trễ trước khi tăng tỷ lệ. Migration nên thêm cấu trúc tương thích trước, chuyển ứng dụng, xác minh dữ liệu rồi mới loại bỏ cấu trúc cũ.

## Kết luận

Cập nhật tại chỗ thay đổi trạng thái của máy đang tồn tại, thuận tiện cho một số hệ thống nhỏ hoặc đặc thù nhưng cần kiểm soát drift và rollback. Mô hình immutable tạo phiên bản mới rồi thay thế đơn vị cũ, hỗ trợ tái tạo, mở rộng và phát hành có kiểm soát khi artifact, cấu hình và dữ liệu được quản lý đúng cách. Quyết định cuối cùng cần xét cả chiến lược rollout, mức sẵn sàng, khả năng tương thích dữ liệu, chi phí chạy song song và năng lực quan sát hệ thống.
