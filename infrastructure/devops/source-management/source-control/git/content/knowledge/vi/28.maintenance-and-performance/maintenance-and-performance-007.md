# Tăng tốc kiểm tra thay đổi với untracked cache và FSMonitor

Trong repository có hàng chục nghìn hoặc hàng trăm nghìn file, `git status` có thể mất nhiều thời gian để xác định file tracked đã thay đổi và tìm file mới chưa được theo dõi. Hai cơ chế của Git giúp giảm công việc quét lặp lại là **untracked cache** và **FSMonitor**. Untracked cache ghi nhớ thông tin về các thư mục đã kiểm tra; FSMonitor thông báo những đường dẫn đã thay đổi kể từ lần kiểm tra trước. Khi filesystem và phiên bản Git hỗ trợ tốt, kết hợp hai cơ chế có thể làm các thao tác kiểm tra trạng thái nhanh hơn đáng kể.

## 1. Vì sao `git status` có thể chậm?

Để xác định trạng thái repository, Git cần đối chiếu nhiều nguồn dữ liệu:

- **HEAD:** snapshot của commit hiện tại.
- **Index:** danh sách file đã stage cùng mode, object ID và metadata cần thiết.
- **Working tree:** file và thư mục hiện có trên ổ đĩa.
- **Untracked files:** file chưa được Git theo dõi nhưng nằm trong phạm vi repository và không bị ignore.

Trong repository nhỏ, việc kiểm tra các file và thư mục thường nhanh. Nhưng với dự án lớn, số lượng file có thể tăng do dependency, generated code, build output, cache hoặc workspace được tạo tự động. Git phải xác định những đường dẫn nào đã thay đổi và thư mục nào chứa file untracked.

Ví dụ, một repository có:

- 80.000 file source và tài nguyên đã tracked.
- 30.000 file build output bị ignore.
- 12.000 file mới chưa được theo dõi.
- Hàng nghìn thư mục con trong workspace.

Nếu Git phải kiểm tra lại metadata của rất nhiều thư mục ở mỗi lần `git status`, thao tác tưởng như đơn giản có thể trở thành nút thắt khi làm việc với IDE, terminal hoặc công cụ tự động.

## 2. Phân biệt untracked cache và FSMonitor

Hai tính năng giảm công việc theo hai cách khác nhau:

| Cơ chế | Ghi nhớ hoặc nhận thông tin gì? | Công việc được giảm |
|---|---|---|
| Untracked cache | Metadata thư mục và thông tin về các file untracked đã phát hiện | Tránh phải liệt kê lại nội dung của những thư mục không thay đổi |
| FSMonitor | Danh sách đường dẫn có thay đổi kể từ một mốc theo dõi | Tránh kiểm tra mọi đường dẫn khi monitor có thể xác định vùng cần kiểm tra |

Untracked cache là dữ liệu cache được lưu trong index của Git. FSMonitor là cơ chế nhận thông báo thay đổi từ filesystem monitor, thông qua daemon tích hợp hoặc một chương trình monitor bên ngoài. Hai cơ chế có thể bổ trợ cho nhau: FSMonitor thu hẹp phạm vi đường dẫn cần kiểm tra, còn untracked cache giúp Git bỏ qua việc quét lại các thư mục untracked không thay đổi.

Không cơ chế nào thay thế index hoặc object database. Chúng chỉ giúp Git xác định trạng thái working tree hiệu quả hơn; nội dung commit và quy tắc quản lý phiên bản vẫn giữ nguyên.

## 3. Untracked cache hoạt động như thế nào?

Untracked cache lưu thông tin về các thư mục đã được Git kiểm tra để tìm file chưa được theo dõi. Khi chạy `git status` lần tiếp theo, Git có thể so sánh metadata của thư mục, chẳng hạn thời điểm sửa đổi và các thông tin filesystem liên quan, để xác định thư mục có cần quét lại hay không.

Nếu thư mục không thay đổi theo thông tin filesystem mà Git dựa vào, Git có thể sử dụng kết quả đã cache thay vì liệt kê lại toàn bộ file bên trong. Nếu thư mục có dấu hiệu thay đổi, Git quét lại thư mục đó và cập nhật cache.

Untracked cache thường hữu ích khi:

- Repository có rất nhiều thư mục con.
- Số lượng file untracked cần phát hiện lớn.
- Cấu trúc thư mục ít thay đổi giữa các lần chạy `git status`.
- Filesystem cung cấp metadata thư mục đáng tin cậy.

Cache này không lưu nội dung file và không thay thế việc kiểm tra file tracked. Git vẫn cần xác minh các file tracked theo cơ chế index và stat data; untracked cache tập trung vào chi phí phát hiện file chưa được theo dõi.

## 4. Điều kiện filesystem cho untracked cache

Untracked cache phụ thuộc vào độ tin cậy của metadata thư mục, đặc biệt là khả năng nhận biết thư mục đã thay đổi. Một số filesystem, mount mạng, đồng bộ thư mục hoặc công cụ bên ngoài có thể cập nhật metadata không theo cách Git mong đợi.

Nếu metadata thư mục không phản ánh chính xác thay đổi, cache có thể trở nên cũ và Git có nguy cơ bỏ sót file untracked mới. Vì vậy, cần kiểm tra khả năng hỗ trợ trước khi bật.

Git cung cấp lệnh:

```bash
git update-index --test-untracked-cache
```

Lệnh này kiểm tra filesystem hiện tại có đáp ứng yêu cầu của untracked cache hay không. Nếu Git báo filesystem không phù hợp, không nên ép bật cache chỉ để thử tăng tốc. Hãy xem xét FSMonitor hoặc cách giảm phạm vi file untracked cần kiểm tra.

Kết quả kiểm tra chỉ phản ánh filesystem và môi trường hiện tại. Nếu repository được chuyển sang ổ đĩa khác, mount khác hoặc môi trường CI khác, hãy kiểm tra lại.

## 5. Bật untracked cache

Sau khi kiểm tra filesystem thành công, bật cache cho repository hiện tại:

```bash
git config --local core.untrackedCache true
```

Git sẽ sử dụng untracked cache khi cập nhật index và kiểm tra trạng thái. Có thể kiểm tra giá trị cấu hình:

```bash
git config --show-origin --get core.untrackedCache
```

Một cách khác là yêu cầu Git bật extension trong index:

```bash
git update-index --untracked-cache
```

Lệnh này bật untracked cache cho index hiện tại. Trong workflow thông thường, cấu hình `core.untrackedCache` giúp biểu đạt chính sách rõ ràng hơn và áp dụng khi Git cập nhật index.

Lần chạy đầu tiên có thể chưa nhanh rõ rệt vì Git phải quét và xây dựng thông tin cache. Hãy chạy `git status` thêm vài lần trên cùng trạng thái repository để đánh giá hiệu quả.

## 6. Tắt untracked cache khi cần

Nếu filesystem có hành vi không đáng tin hoặc bạn nghi ngờ cache làm kết quả untracked không chính xác, tắt ở cấp repository:

```bash
git config --local core.untrackedCache false
```

Có thể loại bỏ extension khỏi index bằng:

```bash
git update-index --no-untracked-cache
```

Sau khi tắt, chạy lại trạng thái và xác minh file untracked xuất hiện đúng:

```bash
git status --short --untracked-files=all
```

Đừng nhầm tắt untracked cache với bỏ qua việc tìm file untracked. Hai việc khác nhau: cache thay đổi cách Git thực hiện kiểm tra, còn `--untracked-files=no` yêu cầu `git status` không liệt kê file untracked trong lần chạy đó.

## 7. FSMonitor là gì?

FSMonitor là giao diện để Git nhận thông báo về các đường dẫn đã thay đổi trong working tree kể từ một mốc theo dõi trước đó. Thay vì phải tự kiểm tra mọi file và thư mục, Git hỏi monitor về những thay đổi đã xảy ra rồi tập trung kiểm tra các đường dẫn liên quan.

Nguồn thông báo có thể là:

- **Built-in FSMonitor daemon:** daemon do Git cung cấp trên nền tảng và phiên bản được hỗ trợ.
- **External FSMonitor hook:** chương trình bên ngoài, chẳng hạn một filesystem watcher được tổ chức hoặc công cụ phát triển cấu hình.

FSMonitor không tự quyết định nội dung file đã thay đổi ra sao. Nó báo cho Git đường dẫn cần kiểm tra; Git vẫn đối chiếu metadata và nội dung cần thiết để xác định trạng thái chính xác.

FSMonitor đặc biệt hữu ích trong repository lớn, nơi phần lớn file không thay đổi giữa các lần `git status`, nhưng số lượng đường dẫn cần theo dõi rất cao.

## 8. Bật built-in FSMonitor daemon

Trên phiên bản Git và nền tảng hỗ trợ built-in FSMonitor, có thể bật bằng cấu hình repository:

```bash
git config --local core.fsmonitor true
```

Kiểm tra daemon:

```bash
git fsmonitor--daemon status
```

Có thể yêu cầu khởi động daemon:

```bash
git fsmonitor--daemon start
```

Trên môi trường hỗ trợ, Git có thể tự khởi động daemon khi cần; lệnh `start` cho phép chủ động kiểm tra và khởi động. Kiểm tra trạng thái sau khi bật:

```bash
git fsmonitor--daemon status
git status --short
```

Khả năng hỗ trợ built-in daemon phụ thuộc phiên bản Git, hệ điều hành và loại filesystem. Nếu lệnh daemon không được hỗ trợ trong môi trường hiện tại, hãy cập nhật Git theo chính sách của tổ chức hoặc sử dụng external monitor đã được xác minh.

## 9. Dùng external FSMonitor hook

`core.fsmonitor` cũng có thể nhận đường dẫn hoặc lệnh của một chương trình monitor bên ngoài. Git gọi chương trình đó theo giao thức FSMonitor để nhận thông tin về các đường dẫn thay đổi.

Về mặt cấu hình, giá trị boolean `true` yêu cầu built-in monitor nếu được hỗ trợ; một giá trị dạng lệnh/path chỉ định external monitor. Ví dụ cấu hình khái quát:

```bash
git config --local core.fsmonitor /path/to/fsmonitor-hook
```

Không sao chép nguyên đường dẫn ví dụ này. Hãy dùng lệnh cài đặt do công cụ monitor chính thức cung cấp và kiểm tra nội dung script trước khi kích hoạt. External monitor là chương trình được Git gọi, do đó cần xem nó như một thành phần thực thi có quyền của tài khoản đang làm việc.

Tránh cấu hình đồng thời built-in daemon và external hook bằng những giá trị mâu thuẫn ở nhiều cấp. Kiểm tra nguồn cấu hình:

```bash
git config --show-origin --show-scope --get core.fsmonitor
```

Nếu có nhiều giá trị từ global và local, xác định giá trị cuối cùng có hiệu lực trước khi điều chỉnh.

## 10. Tắt FSMonitor

Để tắt cấu hình FSMonitor ở repository hiện tại:

```bash
git config --local --unset core.fsmonitor
```

Nếu cấu hình được đặt ở global hoặc system, lệnh trên chỉ gỡ giá trị local; hãy xem nguồn cấu hình trước khi thay đổi cấp khác. Với built-in daemon, có thể dừng tiến trình:

```bash
git fsmonitor--daemon stop
```

Sau đó xác nhận Git không còn dùng monitor ngoài ý muốn:

```bash
git config --show-origin --show-scope --get core.fsmonitor
git status --short
```

Lưu ý `--unset` trả mã thoát khác `0` nếu khóa không tồn tại ở cấp được chỉ định. Điều đó không nhất thiết là lỗi repository; hãy kiểm tra cấu hình thực tế.

## 11. Kết hợp untracked cache và FSMonitor

Hai cơ chế có thể hoạt động cùng nhau. Một workflow điển hình trên filesystem hỗ trợ:

```bash
git update-index --test-untracked-cache
git config --local core.untrackedCache true
git config --local core.fsmonitor true
git status
```

Khi chạy `git status`, Git có thể dùng FSMonitor để biết các đường dẫn đã thay đổi, sau đó dùng index và untracked cache để tránh quét lại những thư mục không có thay đổi liên quan.

Kết quả thường rõ nhất ở repository có nhiều file nhưng chỉ một phần nhỏ thay đổi giữa các lần kiểm tra. Với repository nhỏ, chi phí khởi tạo hoặc duy trì monitor có thể không tạo ra khác biệt đáng kể.

Không cần bật cả hai trong mọi dự án. Hãy đo hiệu năng trước, bật từng cơ chế, kiểm tra tính đúng đắn rồi mới kết hợp để biết lợi ích đến từ đâu.

## 12. Đo hiệu quả trước và sau khi bật

Đừng chỉ dựa vào cảm giác. Hãy đo cùng một lệnh trên cùng repository và cùng trạng thái làm việc.

Trên Bash hoặc Git Bash:

```bash
time git status --short --untracked-files=all
```

Trên PowerShell:

```powershell
Measure-Command { git status --short --untracked-files=all | Out-Host }
```

Quy trình đo:

1. Chọn repository có workload đại diện, đặc biệt là số lượng file untracked và thư mục con.
2. Chạy lệnh vài lần khi chưa bật tính năng và ghi lại thời gian.
3. Bật untracked cache, chạy lại vài lần để cache được tạo và ghi thời gian.
4. Tắt hoặc giữ nguyên untracked cache rồi bật FSMonitor, đo lại.
5. Bật cả hai và đo lần cuối.
6. So sánh thời gian trung vị thay vì chỉ chọn lần chạy nhanh nhất.

Giữ cùng một trạng thái working tree giữa các lượt đo. Nếu thêm hoặc xóa nhiều file giữa các lần, kết quả không còn so sánh trực tiếp được. Lần đầu sau khi bật monitor có thể chậm hơn do daemon khởi động hoặc cache được xây dựng.

Ví dụ bảng ghi kết quả:

| Cấu hình | Lần 1 | Lần 2 | Lần 3 | Nhận xét |
|---|---:|---:|---:|---|
| Mặc định | 2,8 s | 2,6 s | 2,7 s | Mốc ban đầu |
| Untracked cache | 1,7 s | 1,1 s | 1,0 s | Các lần sau giảm thời gian quét thư mục |
| FSMonitor | 1,0 s | 0,8 s | 0,8 s | Chỉ kiểm tra các đường dẫn monitor báo thay đổi |
| Cả hai | 0,6 s | 0,5 s | 0,5 s | Có thể giảm thêm công việc lặp lại |

Các con số trên chỉ minh họa cách ghi nhận, không phải kết quả bảo đảm cho mọi máy hoặc repository.

## 13. Tùy chọn `--untracked-files` và ảnh hưởng tới kết quả

`git status` có thể thay đổi phạm vi tìm file untracked bằng tùy chọn:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--untracked-files=no` hoặc `-uno` | Không liệt kê file untracked |
| `--untracked-files=normal` hoặc `-unormal` | Liệt kê thư mục chứa file untracked thay vì từng file bên trong; đây là mặc định phổ biến |
| `--untracked-files=all` hoặc `-uall` | Liệt kê từng file untracked |

Ví dụ:

```bash
git status --short --untracked-files=no
git status --short --untracked-files=normal
git status --short --untracked-files=all
```

`-uno` có thể làm lệnh trả kết quả nhanh hơn vì Git không cần báo danh sách file untracked, nhưng bạn sẽ không thấy các file mới chưa được theo dõi. Đây là lựa chọn thay đổi thông tin hiển thị, không phải tối ưu cache tương đương với untracked cache hoặc FSMonitor.

Khi kiểm tra hiệu năng untracked cache, hãy giữ cùng một giá trị `--untracked-files` giữa các lần đo. Nếu một lần dùng `no` và lần khác dùng `all`, kết quả không thể so sánh công bằng.

## 14. Giới hạn và trường hợp cần thận trọng

### Untracked cache

- Phụ thuộc metadata thư mục và filesystem; một số filesystem hoặc mount không đáp ứng điều kiện cần thiết.
- Cache cần thời gian được xây dựng, nên lần chạy đầu có thể chưa nhanh.
- Nếu repository được di chuyển giữa filesystem hoặc môi trường khác, hãy kiểm tra lại tính phù hợp.
- Không thay thế kiểm tra file tracked và không làm giảm dung lượng repository.

### FSMonitor

- Cần daemon hoặc external monitor tương thích với Git và filesystem.
- Monitor có thể không khả dụng trong một số môi trường, filesystem mạng hoặc workspace đặc biệt.
- Khi monitor bị dừng, mất trạng thái hoặc không thể cung cấp thông tin đáng tin cậy, Git cần fallback hoặc yêu cầu quét lại để bảo đảm kết quả.
- External hook là chương trình được thực thi; chỉ dùng công cụ từ nguồn đáng tin cậy.
- Một số môi trường CI dùng workspace ngắn hạn, tạo/xóa liên tục; chi phí monitor có thể không đáng so với thời gian chạy job.

Nếu nghi ngờ Git bỏ sót thay đổi, tắt từng tính năng và chạy `git status` lại để đối chiếu. Không tiếp tục commit hoặc tạo quyết định dựa trên trạng thái sai.

## 15. Chẩn đoán khi kết quả không như mong đợi

Kiểm tra cấu hình và trạng thái daemon:

```bash
git config --show-origin --show-scope --get core.untrackedCache
git config --show-origin --show-scope --get core.fsmonitor
git fsmonitor--daemon status
```

Nếu một file untracked mới không xuất hiện:

1. Xác nhận file không bị ignore bằng `git check-ignore -v path/to/file`.
2. Chạy `git status --short --untracked-files=all`.
3. Tạm tắt untracked cache và FSMonitor ở cấp repository rồi chạy lại.
4. Nếu trạng thái chỉ đúng sau khi tắt cache, kiểm tra filesystem và môi trường đồng bộ file.
5. Nếu dùng external monitor, kiểm tra log và giao thức phản hồi của công cụ đó.

Nếu file tracked vừa sửa nhưng `git status` không nhận ra, hãy kiểm tra monitor và stat behavior. Thử tắt FSMonitor trước để xác định vấn đề có liên quan tới monitor hay không. Với filesystem có timestamp độ phân giải thấp hoặc công cụ cập nhật metadata bất thường, cần đánh giá cấu hình Git phù hợp thay vì giả định cache luôn đúng.

Để tắt cả hai trong repository hiện tại khi điều tra:

```bash
git config --local core.untrackedCache false
git config --local --unset core.fsmonitor
git update-index --no-untracked-cache
git status --short --untracked-files=all
```

Sau khi xác nhận kết quả bình thường, có thể bật lại từng tính năng nếu môi trường hỗ trợ. Không xóa index hoặc thư mục `.git` để xử lý sự cố cache.

## 16. Quy trình đề xuất cho repository lớn

1. Đo thời gian `git status --short --untracked-files=all` ở trạng thái mặc định.
2. Chạy `git update-index --test-untracked-cache` để kiểm tra filesystem.
3. Nếu đạt, bật `core.untrackedCache` ở cấp local.
4. Bật built-in FSMonitor nếu phiên bản Git và nền tảng hỗ trợ; nếu dùng external monitor, xác minh nguồn và cấu hình lệnh.
5. Đo lại cùng workload, ghi nhận trung vị và kiểm tra cả trạng thái tracked lẫn untracked.
6. Chạy thử các thao tác thường dùng như `git status`, `git add`, checkout/switch và cập nhật file trong IDE.
7. Nếu kết quả không nhất quán, tắt tính năng liên quan và điều tra filesystem/monitor trước khi tiếp tục.
8. Chỉ đưa cấu hình vào hướng dẫn nhóm khi đã xác nhận trên các hệ điều hành và filesystem mà nhóm thực sự sử dụng.

## 17. Ghi nhớ

Untracked cache giảm việc liệt kê lại các thư mục chưa thay đổi bằng cách lưu thông tin thư mục trong index; FSMonitor báo cho Git những đường dẫn đã thay đổi để thu hẹp phạm vi kiểm tra. Hai cơ chế có thể phối hợp nhưng phụ thuộc vào filesystem, daemon hoặc monitor tương thích. Hãy kiểm tra `git update-index --test-untracked-cache`, bật cấu hình ở phạm vi phù hợp, đo cùng workload trước/sau và xác minh kết quả `git status`. Khi nghi ngờ cache hoặc monitor bỏ sót thay đổi, tắt chúng để đối chiếu trước khi tiếp tục công việc.
