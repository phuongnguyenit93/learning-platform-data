Câu 1: Vì sao pipeline nên triển khai image theo digest thay vì chỉ theo tag?
A. Digest xác định đúng nội dung, dù tag có thể được gán lại.
B. Digest cho phép bỏ qua bước xác thực khi kéo image.
C. Digest tự thay thế layer cũ khi registry nhận bản mới.
D. Digest giữ mọi image cũ dù chính sách retention của registry thay đổi.
Đáp án đúng: A

Câu 2: Khi push một image, registry đã có blob cùng digest trong repository đích. Client thường có thể làm gì?
A. Tải lại blob để cập nhật thời gian tạo của layer.
B. Thay digest blob bằng digest của image manifest.
C. Bỏ qua upload blob đó và gửi các phần còn thiếu.
D. Tạo tag riêng cho mỗi blob trước khi push tiếp.
Đáp án đúng: C

Câu 3: Trong OCI image manifest, các descriptor `config` và `layers` thể hiện thông tin nào?
A. Quyền truy cập của người push và nhóm được pull.
B. Tham chiếu tới blob cấu hình và các layer theo digest.
C. Địa chỉ của registry mirror và thứ tự các endpoint.
D. Lịch sử chạy container và trạng thái của mỗi tiến trình.
Đáp án đúng: B

Câu 4: Khi registry trả `401` kèm `WWW-Authenticate: Bearer`, client cần làm gì để thử lại yêu cầu?
A. Đổi tên tag để registry cấp quyền mặc định.
B. Lấy token đúng scope rồi gửi header Authorization.
C. Bỏ qua token nếu đường truyền đã dùng HTTPS.
D. Gửi password trong body của lệnh pull tiếp theo.
Đáp án đúng: B

Câu 5: Tài khoản robot của job CI chỉ push image vào một repository. Cấp quyền nào phù hợp nhất?
A. Quyền quản trị toàn registry để tránh lỗi phân quyền.
B. Quyền pull toàn cục cho mọi nhóm phát triển.
C. Quyền sửa cấu hình và xoá tất cả repository.
D. Quyền push trong repository đó, kèm pull khi cần.
Đáp án đúng: D

Câu 6: Để chặn triển khai image chưa được ký hợp lệ bằng Cosign, bước kiểm tra nào phù hợp?
A. Xác minh chữ ký theo digest với khóa hoặc danh tính tin cậy.
B. Đối chiếu tên tag với thời gian pipeline chạy gần nhất trong CI.
C. Kiểm tra checksum của tag và bỏ qua danh tính ký.
D. So khớp repository với danh sách image trên runner.
Đáp án đúng: A

Câu 7: Trường hợp sử dụng OCI artifact nào là điển hình đối với registry hỗ trợ OCI?
A. Phân phối token đăng nhập runtime đến từng pod của cluster.
B. Lưu trạng thái pod để thay thế cơ sở dữ liệu của cluster.
C. Thay DNS server bằng một manifest chứa bản ghi phân giải.
D. Phân phối SBOM hoặc Helm chart cùng metadata và blob.
Đáp án đúng: D

Câu 8: Khi thăng hạng image từ staging lên production, cách nào giữ đúng bản đã kiểm thử?
A. Build lại từ cùng commit rồi gán tag của production.
B. Kéo tag `latest` trên staging và push lại dưới tag mới.
C. Sao chép artifact theo digest rồi xác minh tại đích.
D. Đổi tag trong Dockerfile và chạy build tại production.
Đáp án đúng: C

Câu 9: Xóa một tag trên registry nhưng dung lượng lưu trữ chưa giảm. Giải thích nào đúng nhất?
A. Tag luôn chứa một bản sao đầy đủ của mọi layer.
B. Registry phải tính lại digest cho từng blob trước khi xóa.
C. Image chỉ bị xóa khi tất cả runner ngừng pull bằng tag.
D. Blob có thể còn được tham chiếu và cần garbage collection.
Đáp án đúng: D

Câu 10: Image đã được quét và không có CVE mức nghiêm trọng. Vì sao vẫn nên quét lại sau một thời gian?
A. Mỗi lần pull sẽ làm thay đổi các package và metadata của image.
B. Cơ sở dữ liệu lỗ hổng có thể cập nhật dù digest giữ nguyên.
C. Registry luôn sửa lại manifest sau mỗi lần quét image.
D. Tag cũ sẽ tự trỏ sang image mới nếu có bản vá CVE.
Đáp án đúng: B

Câu 11: Một provenance attestation đi kèm image thường hỗ trợ kiểm tra điều gì?
A. Nguồn đầu vào và quá trình build đã tạo ra artifact.
B. Nhóm người dùng có quyền xoá toàn bộ repository.
C. Thời gian sống của token khi client yêu cầu pull.
D. Địa chỉ node sẽ chạy pod sau khi image được kéo.
Đáp án đúng: A

Câu 12: Khi cần rollback nhưng tag phát hành đã từng bị gán lại, nên chọn image như thế nào?
A. Kéo tag `stable` hiện tại và tin vào tên tag cố định.
B. Tạo tag mới từ Dockerfile cũ rồi deploy ngay.
C. Dùng lại digest của bản phát hành trước đã kiểm định.
D. Chọn image có timestamp push cũ nhất trong registry.
Đáp án đúng: C

Câu 13: Cùng một tag phải hỗ trợ `linux/amd64` và `linux/arm64`. OCI image index có vai trò gì?
A. Gộp binary của cả hai kiến trúc vào cùng một layer.
B. Biên dịch lại image khi node dùng kiến trúc khác.
C. Trỏ tới manifest phù hợp cho từng nền tảng đích.
D. Lựa chọn cấu hình CPU của node trước khi pull.
Đáp án đúng: C

Câu 14: Để khôi phục registry sau sự cố mất dữ liệu, bộ sao lưu nào đầy đủ nhất?
A. Blob, metadata/DB và cấu hình liên quan được sao lưu nhất quán.
B. Danh sách tag và lịch sử thao tác trên giao diện quản trị.
C. Cache image trên runner cùng bản sao Dockerfile từ các job CI gần nhất.
D. Các file manifest mới nhất và tên namespace trong registry.
Đáp án đúng: A

Câu 15: Muốn ngăn tag phiên bản `v1.2.0` bị ghi đè sau phát hành, nên cấu hình gì?
A. Đặt lịch tự xóa các tag trước ngày phát hành trên registry.
B. Giảm thời gian sống của access token CI xuống.
C. Chỉ cho phép push tag từ các runner cố định.
D. Áp chính sách tag immutability cho các tag phiên bản.
Đáp án đúng: D

Câu 16: Khi dùng pull-through cache cho upstream registry, nhận định nào đúng?
A. Giảm dung lượng cache, nhưng luôn tải lại mỗi blob từ nguồn.
B. Giảm lượt tải từ upstream, nhưng cần quản lý vòng đời cache.
C. Bỏ xác thực với upstream, nhưng vẫn giữ nguyên quyền push.
D. Khoá được tag ở upstream, nhưng phải thay đổi digest định kỳ.
Đáp án đúng: B
