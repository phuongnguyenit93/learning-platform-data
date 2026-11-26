Trong kiến trúc client-server của Docker Engine, mô tả nào đúng về đường đi của yêu cầu tạo container?
A. Docker CLI gọi trực tiếp runc để tạo container; dockerd chỉ ghi nhận trạng thái sau khi tiến trình bắt đầu.
B. containerd nhận lệnh từ CLI và tự quản lý Dockerfile, cấu hình mạng cùng volume của mọi container.
C. dockerd chỉ phục vụ lệnh tương tác; CLI tự tải image và quản lý writable layer của container.
D. CLI gọi Engine API của dockerd; daemon quản lý đối tượng và ủy quyền tạo container cho containerd.
Đáp án đúng: D

Ứng dụng ghi dữ liệu giao dịch vào /var/lib/app; dữ liệu phải tồn tại độc lập với image và được dùng lại khi container được thay thế; cách nào phù hợp nhất?
A. Dùng docker commit để đóng gói writable layer vào image dùng cho lần tạo kế tiếp.
B. Bật restart policy để Docker giữ nguyên writable layer sau khi container bị xóa.
C. Gắn named volume vào /var/lib/app để dữ liệu có vòng đời độc lập với container.
D. Sao chép thư mục dữ liệu vào image bằng docker build sau mỗi lần ứng dụng cập nhật.
Đáp án đúng: C

Khi viết Dockerfile, nhận định nào mô tả đúng sự khác biệt chính giữa COPY và ADD?
A. ADD tự động nén mọi tệp nguồn trước khi ghi thành một layer mới.
B. COPY có thể tải URL và tự giải nén tar giống ADD trong mọi trường hợp.
C. COPY chép tệp thông thường; ADD còn hỗ trợ URL và giải nén tar cục bộ.
D. RUN cp có thể đọc tệp bất kỳ trên host, kể cả đường dẫn ngoài build context.
Đáp án đúng: C

Một ứng dụng cần compiler để tạo binary nhưng môi trường chạy chỉ cần binary và thư viện runtime; cách xây dựng image nào phù hợp nhất?
A. Biên dịch ở builder stage rồi COPY --from sang runtime stage tối giản.
B. Cài compiler ở stage cuối rồi xóa bằng RUN để loại compiler khỏi mọi layer.
C. Dùng docker commit sau khi build để ẩn compiler khỏi lịch sử image.
D. Biên dịch lại mỗi khi container khởi động bằng cách mount compiler từ host.
Đáp án đúng: A

Một thay đổi nhỏ trong mã nguồn khiến Docker cài lại toàn bộ dependency ở mỗi lần build; cách sắp xếp Dockerfile nào giúp tận dụng cache tốt hơn?
A. Đặt mã nguồn thường đổi trước manifest để cache dependency luôn được giữ nguyên.
B. Cài dependency trước khi chép manifest, vì cache chỉ dựa vào câu lệnh RUN.
C. Gộp mọi tệp vào một layer COPY để sửa mã không chạy lại bước cài thư viện.
D. Chép manifest ổn định, cài dependency rồi chép mã nguồn thường xuyên thay đổi.
Đáp án đúng: D

Build cần tải dependency từ registry riêng bằng token; cách nào giảm nguy cơ token bị lưu trong image layer?
A. Truyền token qua ARG; giá trị tự bị xóa khỏi mọi layer và build metadata.
B. Đặt token trong ENV rồi unset ở RUN kế tiếp để xóa giá trị khỏi layer trước.
C. Dùng BuildKit secret mount ở bước RUN cần token, tránh ghi secret vào image.
D. COPY token vào builder stage rồi xóa tệp ở lệnh RUN cuối của stage đó.
Đáp án đúng: C

Một build context lớn chứa thư mục .git và tệp cấu hình nhạy cảm không cần cho image; biện pháp nào xử lý đúng từ đầu quá trình build?
A. .dockerignore chỉ loại tệp khỏi layer cuối, không thay đổi build context gửi đi.
B. Dùng docker image prune để lọc file không cần thiết khỏi build context.
C. Dùng .dockerignore để loại đường dẫn không cần khỏi build context gửi tới builder.
D. Dùng EXPOSE để ngăn builder nhận thư mục không được khai báo trong Dockerfile.
Đáp án đúng: C

Một container chạy dịch vụ HTTP không cần quyền quản trị host; cấu hình nào thể hiện nguyên tắc đặc quyền tối thiểu tốt nhất?
A. Chạy process bằng USER không đặc quyền, bỏ capability thừa và chỉ cấp quyền ghi cần thiết.
B. Giữ USER root nhưng bỏ NET_ADMIN và mount root filesystem read-only để giảm quyền.
C. Bật --privileged nhưng chỉ publish cổng cần thiết để hạn chế quyền hệ thống.
D. Mount Docker socket read-only để ứng dụng không thể điều khiển daemon host.
Đáp án đúng: A

Khi giới hạn tài nguyên container trên một host dùng chung, mô tả nào đúng về các tùy chọn CPU và bộ nhớ của Docker?
A. --cpus đặt giới hạn RAM, còn --memory xác định số CPU được cấp riêng.
B. CPU shares đặt mức quota cố định, còn --cpus chỉ điều chỉnh trọng số tương đối giữa các container.
C. --memory chỉ giới hạn page cache nên không ảnh hưởng bộ nhớ tiến trình.
D. Dùng --memory giới hạn RAM, --cpus đặt quota CPU; CPU shares chỉ là trọng số khi tranh chấp.
Đáp án đúng: D

Nhiều container cần gọi nhau bằng tên dịch vụ trên cùng Docker host; lựa chọn mạng nào hỗ trợ DNS service discovery tích hợp phù hợp nhất?
A. Tạo user-defined bridge network và kết nối các container cần giao tiếp vào mạng đó.
B. Dùng default bridge vì mọi container trên mạng này luôn phân giải tên tự động.
C. Dùng host network với namespace riêng cho mỗi container rồi NAT cổng qua bridge.
D. Dùng overlay network vì loại mạng này chỉ hoạt động giữa container cùng một host.
Đáp án đúng: A

Một dịch vụ trong container cần được truy cập từ máy host nhưng không được mở ra các interface mạng bên ngoài; cách publish nào phù hợp?
A. Dùng -p 127.0.0.1:8080:80 để bind cổng host vào loopback interface.
B. Dùng EXPOSE 80 vì chỉ thị này tự mở cổng host và giới hạn truy cập nội bộ.
C. Dùng --network host rồi khai báo cổng host 8080 ánh xạ riêng tới cổng container 80.
D. Dùng -p 8080:80 vì Docker mặc định chỉ bind cổng host vào loopback.
Đáp án đúng: A

Một database container cần lưu dữ liệu lâu dài và không phụ thuộc vào vòng đời container; lựa chọn nào mô tả đúng named volume?
A. Bind mount luôn được Docker lưu trong thư mục volume riêng và tự di chuyển khi đổi host.
B. Named volume do Docker quản lý và có thể tồn tại độc lập sau khi container bị xóa.
C. Writable layer của container được chia sẻ giữa mọi container tạo từ cùng image.
D. Named volume chỉ tồn tại trong RAM và tự mất khi máy khởi động lại.
Đáp án đúng: B

Trong Docker Compose, web cần đợi database sẵn sàng trước khi khởi động; cấu hình nào thể hiện đúng điều kiện chờ sức khỏe?
A. Dùng depends_on dạng ngắn vì nó luôn đợi ứng dụng phụ thuộc nhận kết nối thành công.
B. Đặt restart: unless-stopped cho database để Compose chờ đến khi database healthy.
C. Khai báo healthcheck cho database và depends_on với condition: service_healthy ở web.
D. Dùng ports cho database vì Compose kiểm tra cổng đã publish trước khi chạy web.
Đáp án đúng: B

Container có HEALTHCHECK liên tục báo unhealthy nhưng tiến trình chính vẫn chạy; nhận định nào đúng về hành vi mặc định của Docker?
A. Docker gửi SIGKILL và xóa container ngay khi healthcheck thất bại, kể cả khi tiến trình vẫn chạy.
B. Healthcheck failure tự kích hoạt restart policy và tạo một container mới.
C. Healthcheck xóa container khỏi network rồi tạo container thay thế.
D. Healthcheck báo trạng thái sức khỏe; restart policy xử lý khi tiến trình container thoát.
Đáp án đúng: D

Một nhóm muốn người nhận image kiểm tra nguồn gốc quá trình build và danh mục thành phần phần mềm; cách nào phù hợp với BuildKit?
A. Một mutable tag xác định duy nhất bytes của image kể cả sau khi build lại.
B. BuildKit có thể gắn provenance và SBOM attestations để người nhận kiểm tra.
C. docker history xác thực mật mã repository nguồn và danh tính builder cho từng layer.
D. LABEL và EXPOSE cùng chứng minh image không chứa dependency có lỗ hổng.
Đáp án đúng: B

Dockerfile cần để tiến trình ứng dụng làm PID 1, nhận SIGTERM và dừng graceful khi Docker stop; cách khai báo ENTRYPOINT nào phù hợp nhất?
A. Dùng shell-form ENTRYPOINT vì shell luôn chuyển tiếp mọi tín hiệu tới tiến trình con.
B. Dùng exec-form ENTRYPOINT dạng JSON để chạy executable trực tiếp thay vì qua shell.
C. Dùng CMD dạng shell vì Docker gửi SIGKILL trước khi gửi SIGTERM tới PID 1.
D. Khởi chạy ứng dụng nền bằng dấu & để Docker tự theo dõi mọi tiến trình con.
Đáp án đúng: B
