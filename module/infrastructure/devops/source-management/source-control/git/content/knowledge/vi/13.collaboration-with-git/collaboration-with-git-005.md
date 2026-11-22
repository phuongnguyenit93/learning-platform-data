# Pull request và merge request là lớp cộng tác của nền tảng

Git cung cấp commit, branch, merge và các thao tác trao đổi dữ liệu giữa repository. Khi nhiều người cùng phát triển một dự án, nhóm còn cần một nơi để đề xuất thay đổi, xem xét mã nguồn, thảo luận, chạy kiểm tra tự động và quyết định khi nào thay đổi được đưa vào nhánh chính. Các nền tảng lưu trữ Git như GitHub và GitLab cung cấp quy trình này thông qua **Pull Request (PR)** hoặc **Merge Request (MR)**.

PR/MR là tính năng cộng tác của nền tảng, được xây dựng quanh các nhánh và commit Git. Một PR/MR thường mô tả thay đổi từ nhánh nguồn sang nhánh đích, hiển thị phần chênh lệch, ghi nhận ý kiến review, kết quả CI và trạng thái phê duyệt. Nó giúp nhóm đưa ra quyết định có căn cứ trước khi cập nhật nhánh đích.

## 1. PR/MR là gì và vì sao cần lớp cộng tác?

Một Pull Request là đề xuất đưa các thay đổi từ một nhánh vào nhánh khác. GitHub dùng tên **Pull Request**; GitLab dùng tên **Merge Request**. Tên gọi khác nhau, nhưng mục tiêu chung là tạo một không gian làm việc cho việc xem xét và tích hợp thay đổi.

Ví dụ, dự án có nhánh chính `main`. Một thành viên tạo nhánh `feature/payment`, triển khai chức năng thanh toán rồi push nhánh đó lên máy chủ. Thay vì tự đưa commit vào `main`, thành viên mở PR/MR với:

- **Source/head branch**: `feature/payment` — nhánh chứa thay đổi được đề xuất.
- **Target/base branch**: `main` — nhánh dự kiến nhận thay đổi.

Những người có quyền tham gia có thể đọc mô tả, xem commit và diff, để lại nhận xét, yêu cầu chỉnh sửa, phê duyệt hoặc từ chối tích hợp. Pipeline CI có thể chạy để kiểm tra mã nguồn. Khi đáp ứng quy tắc của dự án, một người có quyền sẽ merge đề xuất.

PR/MR không phải là một loại commit đặc biệt trong Git và cũng không tự động thay thế thao tác merge. Đây là đối tượng do nền tảng quản lý, gắn với repository, nhánh nguồn, nhánh đích, nội dung review, các lần chạy kiểm tra và trạng thái xử lý. Thao tác tích hợp cuối cùng vẫn cập nhật lịch sử hoặc ref Git theo chiến lược merge đã chọn.

## 2. PR/MR hoạt động trên các nhánh như thế nào?

Quy trình cơ bản thường diễn ra theo chuỗi:

~~~text
Nhánh main
    |
    +---- tạo nhánh feature/payment
                    |
                    +---- commit thay đổi
                    |
                    +---- push nhánh lên remote
                                  |
                                  +---- mở PR/MR tới main
                                               |
                                  diff + review + CI checks
                                               |
                                      đủ điều kiện tích hợp
                                               |
                                          merge vào main
~~~

PR/MR so sánh nhánh nguồn với nhánh đích tại trạng thái hiện tại. Khi có commit mới được push lên nhánh nguồn, nền tảng thường cập nhật nội dung so sánh và các kiểm tra liên quan. Vì vậy, PR/MR có thể tồn tại qua nhiều vòng review: tác giả sửa code, push commit mới, người review xem lại và thảo luận tiếp.

Ví dụ chuẩn bị nhánh:

~~~bash
git switch main
git pull --ff-only

git switch -c feature/payment
# sửa mã nguồn
git add .
git commit -m "Add payment processing"

git push -u origin feature/payment
~~~

Sau khi push, mở giao diện nền tảng và tạo PR/MR từ `feature/payment` sang `main`. Các lệnh Git ở trên chuẩn bị và xuất bản nhánh; việc tạo PR/MR được thực hiện bằng giao diện web, API hoặc công cụ tích hợp của nền tảng.

Nếu làm việc theo mô hình fork, nhánh nguồn có thể nằm trong repository fork của tác giả, còn nhánh đích nằm trong repository gốc. Trong cùng một repository, cả hai nhánh thường thuộc cùng một remote. Nền tảng có thể hiển thị repository nguồn và repository đích riêng biệt để tránh nhầm lẫn.

## 3. Source/head và target/base branch

Chọn đúng nhánh nguồn và nhánh đích là bước quan trọng khi mở PR/MR.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Source branch / head | Nơi chứa commit được đề xuất | `feature/payment` |
| Target branch / base | Nơi muốn tích hợp thay đổi | `main` |
| Repository nguồn | Repository chứa nhánh nguồn | fork của tác giả hoặc repository nhóm |
| Repository đích | Repository chứa nhánh đích | repository chính của dự án |

Một thay đổi nhỏ có thể được đề xuất vào `main`, nhưng một thay đổi chuẩn bị cho phiên bản kế tiếp có thể cần nhắm tới `release/2.x`. Chọn sai target branch có thể khiến PR/MR hiển thị quá nhiều thay đổi hoặc đưa code vào sai dòng phát triển.

Trước khi tạo, hãy xác nhận:

1. Nhánh nguồn có chứa đúng commit cần review.
2. Nhánh đích là nhánh mà nhóm muốn nhận thay đổi.
3. Repository nguồn và đích đúng, đặc biệt khi làm việc qua fork.
4. Phần diff chỉ gồm những thay đổi thuộc phạm vi đề xuất.

Nếu chọn nhầm target branch, nhiều nền tảng cho phép đổi target sau khi tạo PR/MR. Tuy nhiên, việc đổi target sẽ làm thay đổi tập commit và diff được hiển thị; cần đọc lại toàn bộ nội dung so sánh.

## 4. Nội dung của một PR/MR tốt

PR/MR là tài liệu giải thích thay đổi để người khác có thể đánh giá. Một đề xuất tốt thường có:

- **Tiêu đề rõ ràng**: mô tả kết quả hoặc mục tiêu, ví dụ `Add retry handling for payment requests`.
- **Bối cảnh**: vấn đề nào đang được giải quyết, liên kết issue hoặc yêu cầu liên quan nếu có.
- **Phạm vi**: những gì đã thay đổi và những gì không nằm trong đề xuất.
- **Cách kiểm tra**: lệnh test, kịch bản thủ công hoặc kết quả xác minh.
- **Ảnh minh họa**: nếu thay đổi ảnh hưởng giao diện hoặc trải nghiệm người dùng.
- **Rủi ro và lưu ý triển khai**: migration, cấu hình, feature flag hoặc phụ thuộc cần phối hợp nếu có.

Ví dụ phần mô tả:

~~~markdown
## Mục tiêu
Xử lý việc dịch vụ thanh toán phản hồi chậm bằng cơ chế retry có giới hạn.

## Thay đổi
- Thêm retry cho lỗi tạm thời.
- Giới hạn số lần thử và khoảng chờ.
- Ghi log khi hết số lần thử.

## Kiểm tra
- Chạy unit test cho các trường hợp thành công và timeout.
- Kiểm tra trường hợp nhà cung cấp thanh toán không phản hồi.

## Lưu ý
Không retry các lỗi dữ liệu đầu vào hoặc lỗi xác thực.
~~~

Mô tả cần giúp người review hiểu lý do của thay đổi, cách xác minh và những điểm cần chú ý. Không nên chỉ ghi “fix bug” hoặc “update code” nếu không có thêm ngữ cảnh.

Một số repository cung cấp PR/MR template để thống nhất cấu trúc. Hãy dùng template của dự án và điền các phần phù hợp thay vì xóa các mục bắt buộc.

## 5. Đọc diff và danh sách commit

Nền tảng thường hiển thị các tab hoặc khu vực tương tự:

- **Conversation/Overview**: mô tả, trao đổi, trạng thái và sự kiện của PR/MR.
- **Commits**: danh sách commit nằm trong đề xuất.
- **Files changed/Changes**: diff giữa nhánh nguồn và nhánh đích.
- **Checks/Pipelines**: kết quả kiểm tra tự động.
- **Reviewers/Approvals**: người được yêu cầu review và trạng thái phê duyệt.

Tên tab và cách bố trí thay đổi theo nền tảng, nhưng nội dung cốt lõi tương tự.

Khi đọc diff, người review nên xem cả bối cảnh và tác động:

1. Thay đổi có giải quyết đúng yêu cầu không?
2. Có sửa đúng phạm vi và tránh thay đổi không liên quan không?
3. Có lỗi logic, xử lý biên, vấn đề bảo mật hoặc ảnh hưởng hiệu năng không?
4. Test có kiểm tra hành vi mới và trường hợp lỗi không?
5. Có cần cập nhật tài liệu, cấu hình, migration hoặc log không?

Diff thường được hiển thị theo từng file và từng đoạn dòng. Người review có thể để lại nhận xét ngay tại dòng liên quan. Nếu nhánh nguồn nhận commit mới, nền tảng cập nhật diff; nhận xét gắn với dòng đã thay đổi có thể được đánh dấu là outdated hoặc cần xem lại.

Không nên chỉ đọc tiêu đề commit hoặc phần mô tả. Nội dung diff mới cho thấy chính xác mã nào sẽ được đưa vào nhánh đích.

## 6. Review, comment và approval

Review là quá trình đánh giá thay đổi trước khi tích hợp. Tùy nền tảng và cấu hình dự án, người review có thể:

- Để lại comment chung cho toàn PR/MR.
- Để lại comment gắn với một dòng hoặc đoạn diff.
- Tạo review gồm nhiều nhận xét rồi gửi cùng lúc.
- Phê duyệt thay đổi (Approve).
- Yêu cầu chỉnh sửa (Request changes).
- Đóng PR/MR hoặc trao đổi để tác giả điều chỉnh hướng triển khai.

Một comment là ý kiến hoặc câu hỏi. Nó không nhất thiết đồng nghĩa với việc PR/MR đã được phê duyệt hay bị chặn. Approval là trạng thái review có ý nghĩa theo chính sách của nền tảng và repository. Một số dự án yêu cầu một hoặc nhiều approvals; một số yêu cầu người có vai trò nhất định phê duyệt.

### Phân biệt comment và request changes

| Hành động | Ý nghĩa |
|---|---|
| Comment | Đặt câu hỏi, nêu nhận xét hoặc đề xuất mà không nhất thiết thay đổi trạng thái phê duyệt |
| Approve | Xác nhận thay đổi đạt mức chấp nhận của người review |
| Request changes | Yêu cầu tác giả sửa các vấn đề trước khi tích hợp |
| Resolve conversation | Đánh dấu một luồng thảo luận đã được xử lý; không nhất thiết là approval |

Tác giả nên phản hồi nhận xét bằng cách giải thích hoặc cập nhật code. Khi cần sửa, hãy commit và push lên đúng nhánh nguồn của PR/MR. Nền tảng sẽ cập nhật diff và trạng thái checks theo cấu hình.

Một cuộc thảo luận được resolve không tự chứng minh rằng code đã đúng. Người review vẫn cần kiểm tra phần sửa đổi. Tương tự, một approval có thể bị mất hiệu lực hoặc cần review lại khi có commit mới, tùy quy tắc nền tảng và chính sách repository.

## 7. CI checks và trạng thái pipeline

PR/MR thường kết nối với hệ thống CI để tự động kiểm tra thay đổi. Khi có commit mới, pipeline có thể chạy:

- Unit test và integration test.
- Lint và format check.
- Build ứng dụng.
- Kiểm tra kiểu dữ liệu hoặc phân tích tĩnh.
- Quét lỗ hổng, dependency hoặc secret.
- Kiểm tra migration hay cấu hình triển khai.

Nền tảng hiển thị trạng thái như thành công, thất bại, đang chạy hoặc bị bỏ qua. Tên gọi cụ thể tùy nền tảng và tích hợp CI.

| Trạng thái | Cách hiểu |
|---|---|
| Passed / Success | Kiểm tra đã chạy và đạt yêu cầu |
| Failed | Có ít nhất một kiểm tra thất bại |
| Pending / Running | Kiểm tra chưa hoàn tất |
| Skipped / Neutral | Kiểm tra không chạy hoặc không áp dụng theo cấu hình |
| Required check missing | Một kiểm tra bắt buộc chưa có trạng thái hợp lệ |

Nếu một required check thất bại, nền tảng có thể chặn merge. Tác giả cần xem log của job, xác định nguyên nhân, sửa code hoặc cấu hình rồi push commit mới. Không nên coi việc một pipeline cũ đã thành công là đủ nếu PR/MR đã nhận commit mới và kiểm tra cần chạy lại.

Một check màu xanh chỉ cho biết quy trình kiểm tra được cấu hình đã đạt. Nó không đảm bảo tuyệt đối rằng phần mềm không có lỗi; chất lượng review, test phù hợp và hiểu biết về nghiệp vụ vẫn cần thiết.

## 8. Draft PR/MR và vòng đời đề xuất

Không phải thay đổi nào vừa push cũng sẵn sàng để review. Draft PR/MR (hoặc trạng thái tương đương như Work in progress) cho biết tác giả đang chia sẻ tiến độ nhưng chưa yêu cầu merge chính thức.

Draft hữu ích khi:

- Cần phản hồi sớm về hướng thiết kế.
- Muốn CI chạy trên nhánh đang phát triển.
- Cần cho nhóm xem tiến độ hoặc thảo luận kiến trúc.
- Code chưa hoàn chỉnh hoặc test chưa đầy đủ.

Khi sẵn sàng, tác giả chuyển PR/MR sang trạng thái Ready for review. Người review có thể bắt đầu quy trình review chính thức theo quy định nhóm.

Các trạng thái thường gặp trong vòng đời:

~~~text
Open / Draft
     |
     +---- cập nhật commit và thảo luận
     |
Ready for review
     |
     +---- review + CI + sửa đổi
     |
     +---- đủ điều kiện ----> Merged
     |
     +---- không tiếp tục ---> Closed
~~~

Closed và Merged là hai kết quả khác nhau. Closed nghĩa là đề xuất đã được đóng; thay đổi có thể chưa được đưa vào nhánh đích. Merged nghĩa là nền tảng đã thực hiện hoặc ghi nhận thao tác tích hợp thành công.

Nếu PR/MR bị đóng nhầm hoặc cần tiếp tục, một số nền tảng cho phép mở lại khi điều kiện phù hợp. Nếu nhánh nguồn đã bị xóa hoặc quyền thay đổi, cần khôi phục hoặc push nhánh lại theo quy trình của dự án.

## 9. Các cách merge PR/MR

Khi PR/MR đạt điều kiện, nền tảng có thể cung cấp nhiều chiến lược tích hợp. Tên nút và tùy chọn cụ thể phụ thuộc nền tảng, cấu hình repository và phiên bản dịch vụ.

| Chiến lược | Kết quả lịch sử | Khi thường dùng |
|---|---|---|
| Merge commit | Tạo merge commit kết nối lịch sử nhánh nguồn và nhánh đích | Muốn giữ cấu trúc nhánh và dấu mốc tích hợp |
| Squash and merge | Gộp các thay đổi của PR/MR thành một commit trên nhánh đích | Muốn lịch sử nhánh chính gọn, mỗi đề xuất thành một commit |
| Rebase and merge | Đặt các commit của nhánh nguồn lên trên đầu nhánh đích rồi cập nhật đích mà không tạo merge commit thông thường | Muốn lịch sử tuyến tính và giữ các commit riêng lẻ |

### Merge commit

Merge commit có hai parent (trong trường hợp merge thông thường), ghi nhận việc hợp nhất hai dòng lịch sử. Nó giữ lại cấu trúc phân nhánh và giúp nhận diện thời điểm một nhánh được tích hợp.

### Squash and merge

Nền tảng tạo một commit mới đại diện cho toàn bộ thay đổi của PR/MR rồi đưa commit đó vào nhánh đích. Các commit gốc trên nhánh nguồn vẫn tồn tại trong lịch sử nhánh nguồn, nhưng nhánh đích chỉ nhận commit squash. Chiến lược này phù hợp khi nhóm muốn lịch sử chính gọn và không cần giữ từng commit thử nghiệm.

### Rebase and merge

Nền tảng áp dụng các commit của nhánh nguồn lên trên lịch sử mới nhất của nhánh đích, thường tạo commit mới với hash khác do parent thay đổi. Kết quả thường tuyến tính nhưng không giữ merge commit thể hiện cấu trúc nhánh.

Trước khi chọn, hãy xem chính sách dự án. Nếu nhóm muốn truy vết một PR/MR như một đơn vị tích hợp, merge commit có thể phù hợp. Nếu muốn lịch sử chính ngắn gọn, squash có thể phù hợp. Nếu muốn giữ từng commit nhưng tránh merge commit, rebase and merge là một lựa chọn.

Các chiến lược này có thể chịu thêm điều kiện như fast-forward, linear history hoặc merge method được bật/tắt bởi quản trị viên. Không phải PR/MR nào cũng có tất cả tùy chọn.

## 10. Branch protection và quy tắc merge

Repository thường bảo vệ nhánh quan trọng như `main`, `develop` hoặc nhánh phát hành. Branch protection/ruleset cho phép quản trị viên đặt điều kiện trước khi nhánh được cập nhật.

Các quy tắc có thể bao gồm:

- Không cho phép push trực tiếp hoặc giới hạn người được push.
- Yêu cầu PR/MR trước khi tích hợp.
- Yêu cầu số lượng approval tối thiểu.
- Yêu cầu người review thuộc nhóm hoặc chủ sở hữu mã nguồn phù hợp.
- Yêu cầu các status checks cụ thể phải thành công.
- Yêu cầu mọi conversation được giải quyết.
- Yêu cầu nhánh phải cập nhật với target branch hoặc phải qua merge queue.
- Hạn chế force push và xóa nhánh.

Ví dụ, một nhóm có thể quy định: mọi thay đổi vào `main` phải qua PR/MR, có ít nhất một approval từ người khác tác giả, CI thành công và không còn review thread chưa giải quyết. Khi đó, người tạo PR/MR không thể tự merge nếu các điều kiện chưa đạt hoặc không có quyền.

Tên và cách cấu hình branch protection khác nhau giữa GitHub, GitLab và các nền tảng tự quản lý. Một số chính sách được cấu hình ở cấp repository, một số ở cấp tổ chức hoặc nhóm. Hãy đọc quy định của dự án trước khi tìm cách xử lý một merge bị chặn.

## 11. Cập nhật PR/MR khi nhánh đích thay đổi

Trong khi PR/MR đang mở, nhánh đích có thể nhận commit từ người khác. Điều này có thể làm đề xuất trở nên out-of-date hoặc phát sinh xung đột.

Một cách cập nhật nhánh nguồn là merge nhánh đích vào nhánh nguồn:

~~~bash
git fetch origin
git switch feature/payment
git merge origin/main
# giải quyết xung đột nếu có
git push origin feature/payment
~~~

Cách khác là rebase nhánh nguồn lên nhánh đích mới:

~~~bash
git fetch origin
git switch feature/payment
git rebase origin/main
# giải quyết xung đột nếu có
git push --force-with-lease origin feature/payment
~~~

Rebase viết lại commit của nhánh nguồn, nên việc push sau đó có thể cần cập nhật cưỡng bức. Chỉ làm điều này khi nhánh thuộc quyền kiểm soát của bạn và nhóm cho phép viết lại lịch sử. Nếu nhiều người cùng làm trên nhánh nguồn, hãy phối hợp trước khi rebase.

Một số nền tảng cung cấp nút Update branch hoặc tùy chọn tương đương. Nút này có thể tạo merge commit hoặc dùng phương thức cập nhật do nền tảng cấu hình. Hãy kiểm tra hành vi của nền tảng trước khi sử dụng, nhất là khi nhóm yêu cầu lịch sử tuyến tính.

## 12. Xử lý xung đột trong PR/MR

Xung đột có thể xảy ra khi thay đổi ở nhánh nguồn và nhánh đích cùng sửa một vùng nội dung theo cách Git không thể tự kết hợp. Nền tảng có thể thông báo PR/MR có conflict và không cho merge.

Có thể xử lý trên máy local:

~~~bash
git fetch origin
git switch feature/payment
git merge origin/main
~~~

Nếu Git báo conflict:

1. Chạy `git status` để xem các file cần giải quyết.
2. Mở từng file, đọc các đoạn đánh dấu conflict và quyết định nội dung cuối cùng.
3. Xóa marker conflict, giữ lại phần code đúng và kiểm tra các thay đổi liên quan.
4. Stage file đã giải quyết bằng `git add <file>`.
5. Hoàn tất merge bằng `git commit` nếu Git yêu cầu tạo merge commit.
6. Chạy test phù hợp rồi push nhánh nguồn lên remote.

Với rebase, sau khi giải quyết file và stage, tiếp tục bằng `git rebase --continue`. Nếu cần hủy thao tác rebase đang diễn ra, dùng `git rebase --abort`. Không dùng lệnh hoàn tất merge trong một phiên rebase.

Sau khi push, PR/MR cập nhật diff và nền tảng có thể chạy lại CI. Việc hết conflict chỉ có nghĩa là Git có thể kết hợp lịch sử; nó không chứng minh kết quả giải quyết xung đột đúng về nghiệp vụ. Hãy chạy test và review phần code đã được kết hợp.

## 13. Vai trò của tác giả, reviewer và maintainer

| Vai trò | Trách nhiệm chính |
|---|---|
| Author | Tạo đề xuất, mô tả bối cảnh, giữ diff đúng phạm vi, phản hồi review và cập nhật nhánh nguồn |
| Reviewer | Đọc diff, đánh giá logic, chất lượng, bảo mật và khả năng bảo trì; đưa ra comment hoặc approval |
| Maintainer | Bảo đảm quy trình dự án, quyết định tích hợp theo chính sách, xử lý quyền và nhánh bảo vệ |
| CI/system | Chạy kiểm tra tự động và báo trạng thái cho PR/MR |

Trong nhóm nhỏ, một người có thể đảm nhận nhiều vai trò. Tuy nhiên, các quy tắc như yêu cầu approval từ người khác tác giả giúp tạo thêm một bước kiểm tra độc lập.

Review nên tập trung vào hành vi và rủi ro của thay đổi, không chỉ phong cách cá nhân. Nếu có quy tắc format hoặc lint, hãy tự động hóa chúng bằng công cụ để dành thời gian review cho logic và thiết kế.

## 14. Quy trình cộng tác mẫu từ đầu đến cuối

Giả sử nhóm đang phát triển API thanh toán trên GitHub hoặc GitLab.

**Bước 1 — Đồng bộ nhánh chính và tạo nhánh công việc**

~~~bash
git switch main
git pull --ff-only
git switch -c feature/payment
~~~

**Bước 2 — Phát triển và tạo commit**

~~~bash
# sửa mã nguồn
git status
git diff
git add src/
git commit -m "Add payment endpoint"
~~~

**Bước 3 — Push nhánh nguồn**

~~~bash
git push -u origin feature/payment
~~~

**Bước 4 — Mở PR/MR**

Trên nền tảng, chọn repository nguồn, source branch `feature/payment`, target branch `main`, nhập tiêu đề và mô tả, sau đó tạo PR/MR. Nếu code chưa sẵn sàng, tạo dưới dạng Draft.

**Bước 5 — Chạy kiểm tra và review**

CI chạy test/build/lint theo cấu hình. Reviewer đọc danh sách commit và diff, để lại nhận xét hoặc approval. Tác giả phản hồi và sửa code khi cần.

**Bước 6 — Cập nhật nhánh nguồn**

~~~bash
git add src/
git commit -m "Handle payment timeout"
git push
~~~

PR/MR được cập nhật với commit mới. Các checks cần thiết chạy lại và reviewer xem phần thay đổi tiếp theo.

**Bước 7 — Đạt điều kiện và merge**

Khi review, approvals và checks đều đạt chính sách của dự án, người có quyền chọn chiến lược merge được nhóm cho phép. Nền tảng cập nhật nhánh đích và chuyển PR/MR sang trạng thái Merged.

**Bước 8 — Dọn nhánh**

Sau khi tích hợp, nhánh tính năng thường có thể được xóa trên remote qua giao diện nền tảng hoặc lệnh:

~~~bash
git push origin --delete feature/payment
~~~

Sau đó, cập nhật nhánh local:

~~~bash
git switch main
git pull --ff-only
git branch -d feature/payment
~~~

Chỉ xóa nhánh khi chắc chắn không còn cần tiếp tục phát triển trên đó. Một số nền tảng tự xóa nhánh nguồn sau khi merge nếu repository bật tùy chọn này.

## 15. Những lỗi và hiểu nhầm thường gặp

| Tình huống | Nguyên nhân hoặc cách hiểu đúng |
|---|---|
| PR/MR mở rồi nhưng không thấy thay đổi | Có thể chọn sai source/target, nhánh chưa push hoặc diff không có commit mới |
| PR/MR hiển thị quá nhiều file | Nhánh nguồn có thể chứa commit ngoài phạm vi hoặc target branch không đúng |
| CI thành công nhưng không merge được | Có thể còn thiếu approval, conversation chưa resolve, branch protection hoặc quyền |
| Reviewer đã comment nhưng trạng thái vẫn chưa được approve | Comment và approval là hai hành động khác nhau |
| Đã resolve comment nhưng vẫn bị yêu cầu sửa | Resolve thread chỉ đóng luồng thảo luận; cần xác nhận code đã được sửa và reviewer chấp nhận |
| PR/MR bị conflict | Nhánh nguồn và đích có thay đổi không thể tự kết hợp; cập nhật nhánh nguồn và giải quyết conflict |
| Đã push commit mới nhưng checks vẫn đang chạy | Pipeline cần thời gian hoàn tất; merge có thể bị chặn bởi required checks |
| PR/MR bị Closed | Đề xuất đã đóng, chưa chắc thay đổi đã được merge |
| Merge xong nhưng commit hash khác | Squash hoặc rebase tạo commit mới; đây là hành vi dự kiến của chiến lược đó |

Khi merge bị chặn, hãy đọc thông báo của nền tảng để biết điều kiện nào chưa đạt. Không nên tìm cách bỏ qua branch protection hoặc required checks nếu đó là chính sách của nhóm.

## 16. Bảo mật khi cộng tác qua PR/MR

PR/MR có thể đến từ thành viên nội bộ hoặc contributor bên ngoài, đặc biệt trong dự án dùng fork. Vì vậy, việc review cần xem xét cả mã nguồn và cách pipeline được chạy.

Một số điểm cần chú ý:

- Không đưa token, mật khẩu, private key hoặc thông tin nhạy cảm vào commit, mô tả hay comment.
- Kiểm tra workflow CI có quyền truy cập secret nào khi chạy trên nhánh từ fork.
- Không chạy script hoặc binary chưa tin cậy trên máy có thông tin xác thực quan trọng.
- Xem xét dependency mới, script cài đặt, quyền truy cập và thay đổi cấu hình.
- Kiểm tra migration và thay đổi schema có ảnh hưởng dữ liệu hiện có hay không.
- Với thay đổi nhạy cảm, yêu cầu reviewer phù hợp và áp dụng quy tắc approval của repository.

Các nền tảng có chính sách riêng cho pipeline từ fork, quyền của contributor và secret. Maintainer cần cấu hình quyền tối thiểu và hiểu rõ mã nào được chạy trong CI trước khi bật tự động hóa.

## 17. Những điểm cần ghi nhớ

- PR (GitHub) và MR (GitLab) là tính năng cộng tác của nền tảng lưu trữ Git, dùng để đề xuất tích hợp thay đổi giữa hai nhánh.
- Source/head là nhánh chứa thay đổi; target/base là nhánh nhận thay đổi.
- PR/MR tập hợp mô tả, commit, diff, thảo luận, review, approvals và kết quả CI.
- Comment, approval, request changes và resolve conversation có ý nghĩa khác nhau.
- Draft cho biết đề xuất chưa sẵn sàng review chính thức; Closed không đồng nghĩa Merged.
- Merge commit, squash và rebase tạo ra lịch sử khác nhau; chọn theo quy ước của nhóm.
- Branch protection và required checks giúp bảo đảm thay đổi được review và kiểm tra trước khi vào nhánh quan trọng.
- Khi nhánh đích thay đổi, cập nhật nhánh nguồn bằng merge hoặc rebase rồi kiểm tra lại diff và CI.
- PR/MR hỗ trợ quyết định cộng tác; chất lượng cuối cùng vẫn phụ thuộc vào review có trách nhiệm, test phù hợp và chính sách bảo vệ repository.

Hãy xem PR/MR như một đề xuất có thể kiểm tra và thảo luận: tác giả giải thích thay đổi, reviewer đánh giá, hệ thống chạy kiểm tra, rồi người có quyền tích hợp khi các điều kiện của dự án đã được đáp ứng.

