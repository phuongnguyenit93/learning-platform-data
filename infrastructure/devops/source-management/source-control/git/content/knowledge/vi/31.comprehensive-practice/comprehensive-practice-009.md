# Tìm commit gây lỗi bằng bisect và bài kiểm thử tái hiện

Khi một lỗi xuất hiện trong phiên bản hiện tại nhưng bạn không biết nó bắt đầu từ commit nào, đọc lần lượt toàn bộ lịch sử thường tốn nhiều thời gian. `git bisect` giúp thu hẹp phạm vi bằng cách tìm kiếm nhị phân: bạn cung cấp một commit còn tốt (good) và một commit đã có lỗi (bad), Git lần lượt checkout các commit ở giữa để bạn kiểm tra. Sau mỗi lần đánh giá, Git chọn nửa khoảng lịch sử tiếp theo.

Kết quả có giá trị nhất khi bạn có một **bài kiểm thử tái hiện lỗi** ổn định. Bài kiểm thử phải thất bại ở phiên bản có lỗi, thành công ở phiên bản tốt và cho kết quả nhất quán qua nhiều lần chạy. Khi đã có test như vậy, `git bisect run` có thể tự động chạy test trên từng commit, giúp tìm commit đầu tiên làm phát sinh lỗi.

## 1. Khi nào nên dùng git bisect?

`git bisect` phù hợp khi:

- Một lỗi đã xuất hiện trong branch hiện tại nhưng trước đó tính năng vẫn hoạt động.
- Bạn biết một commit hoặc tag cũ còn tốt và một commit mới đã có lỗi.
- Lịch sử có đủ commit nằm giữa hai mốc để kiểm tra.
- Có thể chạy một thao tác kiểm tra tương đối nhanh trên từng commit.

Ví dụ: ứng dụng thanh toán ở `v2.4.0` không có lỗi, nhưng ở `v2.8.0` việc tính tổng tiền đôi khi trả kết quả sai. Trong khoảng này có 80 commit. Thay vì kiểm tra từng commit theo thứ tự, bisect có thể tìm ra commit gây lỗi sau khoảng 6 đến 7 lần đánh giá nếu lịch sử tuyến tính và không phải bỏ qua commit.

Bạn cần hai mốc đáng tin cậy:

- **Good:** commit mà bài kiểm thử xác nhận hành vi vẫn đúng.
- **Bad:** commit mà bài kiểm thử xác nhận lỗi đã xuất hiện.

Bisect giả định lỗi có một ranh giới tương đối nhất quán trong phạm vi đang kiểm tra: từ mốc tốt đi về phía mốc xấu, có một commit làm trạng thái chuyển từ good sang bad. Nếu lỗi xuất hiện rồi được sửa, phụ thuộc môi trường hoặc chỉ xảy ra theo điều kiện ngẫu nhiên, cần thu hẹp phạm vi hoặc làm test ổn định trước.

## 2. Chuẩn bị trước khi bắt đầu

Trước khi chạy bisect, xác định chính xác lỗi và cách kiểm tra nó. Một mô tả tốt gồm:

1. Đầu vào hoặc điều kiện tái hiện.
2. Kết quả mong đợi.
3. Kết quả thực tế ở phiên bản bị lỗi.
4. Lệnh kiểm tra có thể chạy lặp lại.
5. Các phụ thuộc môi trường cần có như runtime, database, biến môi trường và dịch vụ ngoài.

Ví dụ:

```text
Tình huống: đơn hàng có subtotal = 100 và discount = 10
Mong đợi: total = 90
Thực tế ở v2.8.0: total = 110
Kiểm tra: chạy test payment-total-regression
```

Kiểm tra working tree trước khi bắt đầu:

```bash
git status --short
git branch --show-current
git log --oneline -10
```

Nên commit hoặc lưu riêng thay đổi chưa commit. Trong quá trình bisect, Git checkout nhiều commit và chuyển `HEAD` sang trạng thái detached; thay đổi local có thể cản trở checkout hoặc khiến kết quả kiểm tra không còn phản ánh đúng commit đang thử.

Đảm bảo bạn có đủ lịch sử. Nếu đang dùng shallow clone, cần fetch thêm lịch sử hoặc bỏ giới hạn shallow trước khi bisect. Ví dụ:

```bash
git rev-parse --is-shallow-repository
git fetch --unshallow origin
```

Lệnh `--unshallow` chỉ hoạt động khi remote có thể cung cấp phần lịch sử còn thiếu. Nếu repository đã đầy đủ, không cần chạy lệnh này.

## 3. Tạo bài kiểm thử tái hiện lỗi

Bài kiểm thử tái hiện (regression test) là phép kiểm tra tự động hoặc thủ công chứng minh lỗi đang xảy ra. Test nên tập trung vào hành vi hỏng, không phụ thuộc vào chi tiết triển khai không liên quan.

Một test tốt cần có các đặc điểm:

- **Tái lập:** cùng một commit và cùng môi trường cho cùng kết quả.
- **Phân biệt được good/bad:** pass ở commit tốt, fail ở commit lỗi.
- **Nhanh:** mỗi lần chạy bisect không mất quá nhiều thời gian.
- **Ít phụ thuộc:** tránh gọi mạng, thời gian thực, dữ liệu production hoặc dịch vụ ngoài nếu không cần thiết.
- **Thông báo rõ:** khi fail, cho biết điều kiện nào không đạt.

Ví dụ một test đơn giản bằng JavaScript:

```javascript
import { calculateTotal } from "../src/payment.js";

test("applies discount before returning total", () => {
  const total = calculateTotal({ subtotal: 100, discount: 10 });
  expect(total).toBe(90);
});
```

Test trên chỉ là ví dụ minh họa. Hãy điều chỉnh import, cú pháp và test runner theo dự án thực tế. Quan trọng là cùng một lệnh test phải chạy được trên các commit mà bisect sẽ checkout.

### Test mới có thể chưa tồn tại ở commit cũ

Đây là điểm thường bị bỏ sót. Nếu bạn vừa viết regression test ở commit hiện tại, những commit cũ trong phạm vi bisect có thể chưa chứa file test hoặc chưa có test runner tương ứng. Khi đó, lệnh test sẽ báo lỗi vì thiếu file, và Git có thể hiểu nhầm đó là commit bad nếu script trả mã thoát thông thường.

Có một số cách xử lý:

1. Dùng một test hoặc script đã tồn tại xuyên suốt khoảng commit cần kiểm tra.
2. Đặt test harness bên ngoài working tree và cho nó kiểm tra mã nguồn của commit hiện tại.
3. Dùng script bisect áp dụng test patch tạm thời lên từng commit, chạy test, rồi dọn patch trước lần checkout tiếp theo.
4. Thu hẹp khoảng lịch sử đến mốc mà test runner và cấu trúc dự án đã tồn tại.

Nếu dùng test harness bên ngoài repository, hãy bảo đảm nó luôn đọc mã nguồn trong working tree đang được bisect, không vô tình import một bản cài đặt cũ hoặc dùng artifact build từ commit khác. Có thể cần xóa cache và build output giữa các lần chạy.

## 4. Bắt đầu phiên bisect thủ công

Cú pháp thông dụng:

```bash
git bisect start
git bisect bad <bad-commit>
git bisect good <good-commit>
```

Ví dụ, `HEAD` hiện tại đã có lỗi và tag `v2.4.0` còn tốt:

```bash
git bisect start
git bisect bad HEAD
git bisect good v2.4.0
```

Bạn cũng có thể cung cấp hai mốc ngay khi bắt đầu:

```bash
git bisect start HEAD v2.4.0
```

Trong cú pháp ngắn này, đối số đầu là mốc bad và đối số sau là mốc good. Khi phiên bisect bắt đầu, Git checkout một commit ở giữa khoảng lịch sử. `HEAD` thường ở detached state; đó là hành vi bình thường.

Kiểm tra commit đang được thử:

```bash
git status --short
git log -1 --oneline --decorate
git rev-parse HEAD
```

Chạy bài kiểm thử tái hiện lỗi trên commit đó. Nếu test pass, đánh dấu good:

```bash
git bisect good
```

Nếu test fail đúng theo lỗi cần tìm, đánh dấu bad:

```bash
git bisect bad
```

Git dùng kết quả mới để chọn commit tiếp theo trong phạm vi còn lại. Tiếp tục chạy test và đánh dấu cho đến khi Git xác định commit đầu tiên làm trạng thái chuyển từ good sang bad.

## 5. Hiểu quá trình tìm kiếm nhị phân

Giả sử lịch sử tuyến tính có các commit từ A đến H:

```text
A---B---C---D---E---F---G---H
    good                    bad
```

Bạn biết B còn tốt và H đã lỗi. Git chọn một commit ở giữa, ví dụ E:

```text
A---B---C---D---E---F---G---H
    good        ?           bad
```

Nếu E good, lỗi chỉ có thể nằm ở phần sau E; nếu E bad, lỗi nằm trong phần từ sau B đến E. Git tiếp tục chia đôi phạm vi còn lại.

Với khoảng 64 commit cần phân biệt, tìm kiếm nhị phân thường cần khoảng 6 lần đánh giá thay vì kiểm tra tuần tự 63 commit. Con số thực tế có thể tăng khi có commit bị skip, lịch sử merge phức tạp hoặc test không chạy được ở một số revision.

Bạn có thể xem trạng thái và lịch sử phiên bisect:

```bash
git bisect log
git bisect visualize
```

`git bisect visualize` mở danh sách/đồ thị các commit còn liên quan bằng công cụ log được cấu hình. Nếu muốn xem các mốc good/bad đã đánh dấu, `git bisect log` là nguồn dễ kiểm tra và lưu lại.

## 6. Bỏ qua commit không thể kiểm tra bằng git bisect skip

Một số commit không thể build hoặc chạy test vì thiếu dependency, lỗi build tạm thời hoặc cấu trúc dự án chưa hoàn chỉnh. Không nên tự động đánh dấu những trường hợp đó là bad.

Dùng:

```bash
git bisect skip
```

Git sẽ loại commit hiện tại khỏi các phép đánh giá và chọn commit khác. Có thể skip một hoặc nhiều revision:

```bash
git bisect skip <commit-1> <commit-2>
```

Nếu các commit quanh ranh giới đều bị skip, Git có thể không xác định được duy nhất một commit đầu tiên bị lỗi. Kết quả có thể là một khoảng hoặc một tập commit ứng viên. Khi đó, cần cải thiện test/harness, bổ sung mốc good/bad hoặc kiểm tra thủ công các commit còn lại.

Chỉ dùng `skip` khi thực sự không thể phân loại commit. Nếu test fail đúng vì lỗi đang điều tra, phải đánh dấu bad; nếu test pass, đánh dấu good.

## 7. Tự động hóa bằng git bisect run

Khi đã có một lệnh kiểm thử có thể phân loại commit, dùng `git bisect run` để Git tự chạy lệnh đó ở mỗi revision:

```bash
git bisect start
git bisect bad HEAD
git bisect good v2.4.0
git bisect run <command> [<arg>...]
```

Ví dụ nếu test runner đã có trong mọi commit của phạm vi:

```bash
git bisect run npm test -- --runInBand tests/payment-regression.test.js
```

Git checkout commit tiếp theo, chạy lệnh, đọc mã thoát và tự đánh dấu good, bad hoặc skip. Sau đó nó lặp lại cho đến khi tìm được commit đầu tiên có lỗi hoặc không thể phân biệt rõ do quá nhiều commit bị skip.

### Quy ước mã thoát của lệnh được bisect run

Mã thoát rất quan trọng. `git bisect run` hiểu kết quả như sau:

| Mã thoát | Ý nghĩa đối với bisect |
|---:|---|
| `0` | Commit good: test pass |
| `1` đến `124` | Commit bad: test fail |
| `125` | Skip commit: không thể kiểm tra/phân loại revision này |
| `126`, `127` | Được xem là bad theo quy tắc mã thoát, thường là lỗi không chạy được lệnh; cần tránh để lỗi môi trường bị hiểu nhầm là lỗi sản phẩm |
| `128` trở lên | Dừng phiên `bisect run` do lệnh kết thúc bất thường hoặc bị signal |

Vì `126` và `127` vẫn thuộc nhóm bad, script nên kiểm tra trước các công cụ và file cần thiết. Nếu thiếu dependency hoặc test không thể chạy vì lý do môi trường, script phải trả `125` để skip thay vì trả mã lỗi khiến commit bị đánh dấu bad. Mã `128` hoặc lớn hơn làm `bisect run` dừng lại.

## 8. Viết script kiểm thử cho bisect run

Một script shell có thể chuẩn hóa kết quả test thành ba trạng thái: pass, fail và không thể đánh giá.

Ví dụ `bisect-test.sh`:

```bash
#!/bin/sh

# Không thể kiểm tra nếu thiếu runtime hoặc test harness.
command -v npm >/dev/null 2>&1 || exit 125
[ -f package.json ] || exit 125
[ -f tests/payment-regression.test.js ] || exit 125

# Chạy đúng test tái hiện lỗi.
npm test -- --runInBand tests/payment-regression.test.js
result=$?

if [ "$result" -eq 0 ]; then
    exit 0
fi

# Test runner có thể dùng 125 để báo không thể đánh giá.
if [ "$result" -eq 125 ]; then
    exit 125
fi

# Các lỗi test còn lại được xem là trạng thái bad.
exit 1
```

Đặt script ở vị trí có thể truy cập trong suốt phiên bisect. Nếu script nằm trong repository nhưng không tồn tại ở các commit cũ, checkout có thể làm nó biến mất. Có thể đặt script ngoài working tree, hoặc bảo đảm script được giữ nguyên và không bị Git ghi đè tại các revision được kiểm tra.

Chạy:

```bash
chmod +x /path/to/bisect-test.sh
git bisect run /path/to/bisect-test.sh
```

Script mẫu trên giả định test runner trả `0` khi pass và mã khác `0` khi test fail. Nếu công cụ kiểm thử có thể trả mã khác cho lỗi hạ tầng, hãy phân biệt rõ lỗi hạ tầng với lỗi assertion và chuyển lỗi hạ tầng sang `125`. Không biến mọi lỗi build hoặc lỗi thiếu dependency thành bad.

### Lưu ý khi chạy trên Windows

Git for Windows thường cung cấp shell `sh` thông qua Git Bash. Bạn có thể chạy script POSIX bằng cách gọi `sh` rõ ràng:

```bash
git bisect run sh /c/tools/bisect-test.sh
```

Đường dẫn phải phù hợp với môi trường shell mà Git gọi. Nếu dùng PowerShell script, hãy gọi PowerShell với đường dẫn tuyệt đối và bảo đảm mã thoát được trả về đúng quy ước `0`, `1`–`124`, `125` hoặc từ `128` trở lên. Hãy thử chạy script độc lập trên một commit good và một commit bad trước khi bắt đầu tự động hóa toàn bộ lịch sử.

## 9. Xây dựng test ổn định qua nhiều phiên bản

Một test có thể chạy tốt ở `HEAD` nhưng thất bại ở commit cũ vì API test runner đã đổi, dependency chưa tồn tại hoặc cấu trúc module khác. Đó chưa chắc là lỗi cần tìm.

Để tăng độ tin cậy:

- Dùng test ở mức hành vi công khai thay vì phụ thuộc tên hàm nội bộ nếu API đã thay đổi.
- Pin hoặc cài dependency theo lockfile của từng commit khi có thể.
- Xóa build output và cache được tạo từ revision trước nếu chúng có thể ảnh hưởng kết quả.
- Dùng fixture và dữ liệu cố định; không phụ thuộc thời gian hiện tại, thứ tự test ngẫu nhiên hoặc dịch vụ mạng.
- Giữ cùng phiên bản runtime/toolchain nếu có thể; nếu dự án thay đổi toolchain trong khoảng bisect, phân loại commit không build được là skip cho đến khi môi trường phù hợp.
- Kiểm tra script trên ít nhất một commit chắc chắn good và một commit chắc chắn bad trước khi chạy `git bisect run`.

Nếu lỗi chỉ xảy ra khi dùng database hoặc service bên ngoài, tạo môi trường test cô lập hoặc stub dữ liệu để test có thể chạy lặp lại. Mỗi lần bisect nên bắt đầu từ trạng thái môi trường sạch, không tái sử dụng database đã bị lần chạy trước làm thay đổi.

## 10. Khi lịch sử có merge commit

Lịch sử không phải lúc nào cũng là một đường thẳng. Merge commit có nhiều parent và một lỗi có thể xuất hiện do kết hợp hai nhánh, dù từng nhánh riêng lẻ không lỗi.

Mặc định, bisect xét đồ thị commit và tìm theo các revision trong phạm vi. Nếu muốn giới hạn kiểm tra theo lịch sử first-parent (ví dụ chỉ quan tâm các commit được đưa vào nhánh chính qua merge), có thể bắt đầu:

```bash
git bisect start --first-parent HEAD v2.4.0
```

`--first-parent` đi theo chuỗi parent thứ nhất, phù hợp với một số workflow merge vào mainline. Tuy nhiên, nó có thể bỏ qua commit bên trong nhánh feature đã tạo lỗi. Nếu lỗi được đưa vào qua một commit nằm trong nhánh phụ, bisect toàn bộ đồ thị có thể cần thiết hơn.

Nếu merge commit là commit đầu tiên có lỗi, hãy kiểm tra cả hai parent và các thay đổi được hợp nhất:

```bash
git show --cc <MERGE_COMMIT>
git diff <MERGE_COMMIT>^1 <MERGE_COMMIT>
git diff <MERGE_COMMIT>^2 <MERGE_COMMIT>
```

Những lệnh này giúp xác định khác biệt giữa merge result và từng parent. Đừng kết luận lỗi nằm ở một commit trong nhánh phụ chỉ vì merge commit được đánh dấu bad; lỗi có thể xuất hiện từ cách giải quyết conflict hoặc tương tác giữa hai nhánh.

## 11. Tìm hiểu commit được xác định

Khi Git tìm ra commit đầu tiên có lỗi, nó hiển thị commit đó cùng thông báo `first bad commit`. Ghi lại OID và xem chi tiết:

```bash
git show --stat <BAD_COMMIT>
git show --format=fuller <BAD_COMMIT>
git diff <BAD_COMMIT>^ <BAD_COMMIT>
```

Đọc nội dung thay đổi, tác giả, thời gian và parent commit. Nếu commit có nhiều thay đổi, kiểm tra từng file và liên hệ với test tái hiện.

Bạn cũng có thể xem log của phiên bisect:

```bash
git bisect log
```

Lưu log này vào ghi chú sự cố hoặc ticket để người khác có thể hiểu những mốc good/bad/skip đã dùng. Không nên chỉ gửi tên commit mà không kèm test, môi trường và cách tái hiện; những thông tin đó giúp kết luận có thể kiểm chứng.

Sau khi điều tra xong, thoát phiên bisect và trở về branch trước đó:

```bash
git bisect reset
```

Lệnh reset kết thúc trạng thái bisect và checkout lại vị trí ban đầu (hoặc revision được chỉ định). Kiểm tra:

```bash
git status --short
git branch --show-current
```

Nếu có thay đổi thử nghiệm trong working tree, hãy lưu hoặc dọn chúng theo cách phù hợp trước khi reset; không để chúng bị mất khi checkout.

## 12. Lệnh bisect hữu ích khác

| Lệnh | Công dụng |
|---|---|
| `git bisect start` | Bắt đầu phiên bisect |
| `git bisect good <rev>` | Đánh dấu revision là good |
| `git bisect bad <rev>` | Đánh dấu revision là bad |
| `git bisect skip [<rev>...]` | Bỏ qua revision không thể đánh giá |
| `git bisect log` | In lại các bước đã đánh dấu |
| `git bisect replay <file>` | Phát lại một log bisect đã lưu |
| `git bisect visualize` | Xem các commit còn trong phạm vi tìm kiếm |
| `git bisect terms` | Xem tên term good/bad hiện tại |
| `git bisect reset` | Kết thúc bisect và quay về vị trí ban đầu |

Nếu muốn dùng tên khác thay cho good/bad, có thể cấu hình term:

```bash
git bisect start --term-new=broken --term-old=fixed
git bisect broken HEAD
git bisect fixed v2.4.0
```

Điều này hữu ích khi nhóm muốn dùng ngôn ngữ phù hợp với sự cố, nhưng cần nhất quán giữa các lệnh. `broken` tương ứng bad; `fixed` tương ứng good trong ví dụ.

## 13. Những lỗi thường gặp khi dùng bisect

### Chọn sai mốc good hoặc bad

Nếu commit good thực tế đã có lỗi hoặc commit bad thực tế chưa lỗi, kết quả có thể sai. Chạy test tái hiện trên cả hai mốc trước khi bắt đầu. Nếu không chắc, tìm mốc khác hoặc kiểm tra thêm tag/release gần đó.

### Test không ổn định

Test lúc pass lúc fail do race condition, thời gian, mạng hoặc dữ liệu ngẫu nhiên sẽ khiến bisect phân loại sai commit. Hãy cô lập test, cố định fixture và chạy lặp lại trước khi tự động hóa.

### Môi trường bị thay đổi giữa các commit

Dependency hoặc runtime có thể không tương thích với commit cũ. Phân biệt lỗi sản phẩm với lỗi môi trường; dùng `skip` cho revision không thể kiểm tra thay vì đánh dấu bad.

### Test harness không có ở commit cũ

Nếu script hoặc test file nằm trong repository và bị checkout mất ở revision cũ, `bisect run` có thể phân loại sai. Đặt harness bên ngoài working tree hoặc bảo đảm nó tồn tại trong mọi revision cần kiểm tra.

### Bỏ quên detached HEAD

Trong phiên bisect, `HEAD` thường không ở branch. Không tạo commit sửa lỗi ngay trong trạng thái đó nếu chưa có chủ đích; trước hết kết thúc bisect hoặc tạo branch cứu hộ nếu cần lưu một thử nghiệm.

### Quên reset sau khi tìm ra commit

Sau khi ghi lại kết quả, chạy `git bisect reset` để quay lại branch ban đầu. Nếu quên, bạn có thể tiếp tục làm việc trên một commit detached mà không nhận ra.

## 14. Quy trình điều tra mẫu từ đầu đến cuối

Giả sử lỗi tính tổng thanh toán xuất hiện ở `HEAD`, trong khi tag `v2.4.0` còn tốt. Bạn đã có test tái hiện ổn định và script harness bên ngoài working tree.

**Bước 1: Kiểm tra trạng thái và mốc**

```bash
git status --short
git show --no-patch --oneline HEAD
git show --no-patch --oneline v2.4.0
```

Chạy test trên `HEAD` để xác nhận fail và trên `v2.4.0` để xác nhận pass.

**Bước 2: Bắt đầu bisect**

```bash
git bisect start
git bisect bad HEAD
git bisect good v2.4.0
```

**Bước 3: Tự động chạy test**

```bash
git bisect run /path/to/bisect-test.sh
```

Git lần lượt checkout các commit và chạy harness. Harness trả `0` nếu test pass, `1` nếu test fail đúng lỗi đang tìm và `125` nếu commit không thể đánh giá.

**Bước 4: Xem commit đầu tiên bị lỗi**

```bash
git show --stat <BAD_COMMIT>
git show <BAD_COMMIT>
git bisect log
```

Đối chiếu thay đổi trong commit với điều kiện tái hiện. Nếu kết quả không hợp lý, kiểm tra lại test, mốc good/bad và các commit bị skip.

**Bước 5: Kết thúc phiên**

```bash
git bisect reset
git status --short
```

Ghi nhận OID commit, test đã chạy, môi trường, số commit bị skip và kết luận để nhóm có thể xác nhận độc lập.

## 15. Bài tập thực hành

Trong repository thử nghiệm, tạo một lịch sử có khoảng 8–16 commit. Một commit ở giữa cố ý đưa vào lỗi tính toán; các commit sau tiếp tục sửa tài liệu hoặc thêm tính năng nhưng vẫn giữ lỗi.

1. Tạo test tái hiện lỗi và xác nhận test pass ở commit trước lỗi, fail ở commit sau lỗi.
2. Bắt đầu `git bisect`, đánh dấu hai mốc good và bad.
3. Quan sát các commit trung gian được checkout, chạy test và đánh dấu bằng `good`/`bad`.
4. Lặp lại phiên bisect bằng `git bisect run` với một script trả đúng mã thoát.
5. Cố ý làm một commit không thể build và điều chỉnh script để trả `125`; quan sát cách Git bỏ qua commit.
6. Xem `git bisect log`, ghi lại commit đầu tiên bị lỗi và dùng `git show` để phân tích thay đổi.
7. Chạy `git bisect reset`, xác nhận branch ban đầu và working tree đã trở lại trạng thái mong muốn.
8. Thử một test không ổn định hoặc phụ thuộc môi trường trong repository thử nghiệm, giải thích vì sao kết quả bisect có thể sai và cách làm test ổn định hơn.

Bạn hoàn thành bài tập khi tìm được commit gây lỗi bằng cả cách đánh dấu thủ công và `git bisect run`, giải thích được vai trò của test tái hiện và phân loại đúng commit good, bad, skip.
