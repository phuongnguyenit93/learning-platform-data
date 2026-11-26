Câu 1. Thư viện ở `1.7.4` thêm chức năng mới và giữ tương thích ngược với API công khai. Theo SemVer, nên tăng lên bản nào?
A. Phát hành `1.7.5` theo quy tắc dành cho bản sửa lỗi patch.
B. Phát hành `2.0.0` vì đây là mức tăng major.
C. Giữ `1.7.4+feature.1` như một bản sửa mới.
D. Phát hành `1.8.0` vì đây là mức tăng minor.
Đáp án đúng: D

Câu 2. Thư viện ở `2.6.3` xóa một phương thức API khiến mã client cũ không còn biên dịch. Bước tăng phiên bản SemVer nào phù hợp?
A. Tăng lên `2.6.4` để đánh dấu bản sửa API.
B. Tăng lên `2.7.0` để thêm thay đổi API mới.
C. Tăng lên `3.0.0` vì thay đổi phá tương thích.
D. Giữ `2.6.3-rc.1` vì chưa cần tăng version release.
Đáp án đúng: C

Câu 3. Theo SemVer, so sánh thứ tự phiên bản `2.4.0-rc.2` và `2.4.0` cho kết quả nào?
A. `2.4.0-rc.2` được xếp trước `2.4.0`.
B. `2.4.0-rc.2` được xếp sau `2.4.0`.
C. `2.4.0-rc.2` ngang thứ tự với `2.4.0`.
D. `2.4.0-rc.2` không phải phiên bản hợp lệ.
Đáp án đúng: A

Câu 4. So sánh `1.8.0+build.7` và `1.8.0+build.9` theo quy tắc precedence của SemVer. Kết luận nào đúng?
A. Hai bản có cùng thứ tự ưu tiên dù metadata khác nhau.
B. Bản `+build.9` có precedence cao hơn do metadata số lớn.
C. Bản `+build.7` có thứ tự ưu tiên cao hơn `+build.9`.
D. Cả hai bản không hợp lệ vì chứa dấu cộng metadata.
Đáp án đúng: A

Câu 5. Với hai bản prerelease `1.0.0-rc.2` và `1.0.0-rc.10`, SemVer xác định thứ tự nào?
A. Bản `rc.2` cao hơn nếu so `2` với ký tự đầu của `10`.
B. Hai bản có thứ tự bằng nhau do cùng prefix `rc`.
C. `rc.10` không hợp lệ do phần số có hai chữ số.
D. `rc.10` cao hơn do định danh số `10` lớn hơn `2`.
Đáp án đúng: D

Câu 6. Chuỗi nào vi phạm cú pháp SemVer 2.0.0 vì định danh số của prerelease có số 0 đứng đầu?
A. `1.2.3-alpha.01`
B. `1.2.3-alpha.1`
C. `1.2.3+build.001`
D. `1.2.3-rc.0`
Đáp án đúng: A

Câu 7. Vì sao thư viện đang ở phiên bản `0.8.2` chưa thể hiện cam kết API ổn định như mốc `1.0.0` trong SemVer?
A. Vì mọi bản `0.y.z` đều phải phá tương thích API.
B. Vì API ở `0.y.z` vẫn được xem là chưa ổn định.
C. Vì `0.y.z` cấm bổ sung tính năng tương thích ngược.
D. Vì `0.y.z` không hỗ trợ phần prerelease metadata.
Đáp án đúng: B

Câu 8. Thư viện đang ở `4.2.6` chỉ sửa lỗi và không thay đổi API công khai. Phiên bản SemVer kế tiếp hợp lý là gì?
A. Đổi thành `4.3.0` vì có thay đổi trong mã nguồn.
B. Đổi thành `4.2.7` vì đây là bản sửa lỗi patch.
C. Đổi thành `5.0.0` vì bản build đã được cập nhật.
D. Đổi thành `4.2.6+fix.1` như một bản patch mới.
Đáp án đúng: B

Câu 9. Nhóm cần Git tag `v1.4.0` chứa thông điệp phát hành và thông tin người tạo tag. Loại tag nào phù hợp nhất?
A. Tạo lightweight tag trên commit được phát hành.
B. Đổi tên nhánh phát hành thành `v1.4.0` trong Git.
C. Đưa thông điệp release vào commit được đánh dấu.
D. Tạo annotated tag có metadata và thông điệp tag.
Đáp án đúng: D

Câu 10. Pipeline định chuyển tag release `v1.3.0` đã công bố sang commit mới. Theo chính sách tag bất biến, nên xử lý thế nào?
A. Force-push lại `v1.3.0` rồi giữ lịch sử CI hiện tại.
B. Gỡ tag `v1.3.0` trên remote rồi gắn vào commit mới.
C. Giữ nguyên tag cũ và phát hành phiên bản mới.
D. Đổi tag trên remote nếu artifact vẫn cùng tên file.
Đáp án đúng: C

Câu 11. Pipeline cần phiên bản `1.5.0` vừa thể hiện prerelease `rc.1` vừa gắn build metadata `sha.abc`. Chuỗi nào biểu diễn đúng?
A. `1.5.0+rc.1-sha.abc`
B. `1.5.0-rc.1.sha.abc`
C. `1.5.0-rc.1+sha.abc`
D. `1.5.0+sha.abc-rc.1`
Đáp án đúng: C

Câu 12. Đội muốn changelog theo từng bản release để người nâng cấp biết thay đổi nào đã được phát hành. Cách tổ chức nào hữu ích nhất?
A. Liệt kê toàn bộ commit theo ngày mà không phân phiên bản.
B. Chỉ ghi danh sách thành viên và thời điểm triển khai.
C. Thay changelog bằng số lần pipeline đã chạy trong tuần.
D. Gắn thay đổi với phiên bản/tag và mô tả ảnh hưởng.
Đáp án đúng: D

Câu 13. Dự án đang ở `1.x` và có automation theo Conventional Commits. Ánh xạ nào phù hợp để đề xuất mức tăng SemVer?
A. `BREAKING CHANGE` → minor, `feat` → major, `fix` → patch.
B. `BREAKING CHANGE` → major, `feat` → minor, `fix` → patch.
C. `BREAKING CHANGE` → patch, `feat` → minor, `fix` → major.
D. `BREAKING CHANGE` → major, `feat` → patch, `fix` → minor.
Đáp án đúng: B

Câu 14. Bản `3.2.0` đã kiểm thử ở staging. Để production dùng đúng các byte của bản đã kiểm thử, pipeline nên làm gì?
A. Build lại từ Git tag `v3.2.0` trên runner giống môi trường staging.
B. Promote chính artifact theo digest đã kiểm thử sang production.
C. Build lại từ cùng Git SHA trên runner dành cho production.
D. Chạy lại bước đóng gói ở production với cùng version.
Đáp án đúng: B

Câu 15. Sau sự cố, đội cần rollback về đúng binary `v2.4.1` từng chạy ổn định. Thao tác nào đáng tin cậy nhất?
A. Triển khai lại artifact theo digest đã lưu của `v2.4.1`.
B. Checkout tag `v2.4.1` rồi build lại trên CI với cùng script cũ.
C. Dùng image tag `stable` đang có trên registry hiện tại.
D. Cherry-pick commit cũ và tạo artifact mới cùng version.
Đáp án đúng: A

Câu 16. Muốn truy vết chính xác binary đang chạy dù tag registry có thể được gắn lại, bản ghi triển khai cần bộ thông tin nào?
A. Tên nhánh, mã sprint, thời gian build và runner ID.
B. Tên tag, tên reviewer, danh sách issue và job log.
C. Digest artifact, Git SHA, môi trường và thời điểm triển khai.
D. Version hiển thị, changelog và ngày duyệt merge request gần nhất.
Đáp án đúng: C
