# Hoàn thành mã và tra cứu tài liệu ngay trong phiên JShell

JShell là công cụ tương tác của JDK. Ngoài việc chạy từng snippet Java, JShell còn hỗ trợ hoàn thành mã, gợi ý import, xem tài liệu API tại vị trí nhập liệu, chỉnh sửa snippet và chạy lại mã đã nhập. Những thao tác này giúp khám phá API và thử nghiệm ý tưởng ngay trong phiên làm việc.

Các tính năng trong bài thuộc JShell hiện hành, được đưa vào JDK từ Java 9 và tiếp tục được hỗ trợ trong các JDK mới.

## 1. Hoàn thành mã bằng phím Tab

Khi đang nhập trong dấu nhắc JShell, nhấn **Tab** sau một phần tên Java hoặc lệnh JShell. Công cụ có thể hoàn thành:

- Tên identifier Java như biến, phương thức, lớp hoặc package.
- Tên lệnh JShell, ví dụ tiền tố `/li` có thể hoàn thành thành `/list`.
- Một số đối số của lệnh JShell, tùy ngữ cảnh.

Nếu có nhiều lựa chọn, JShell hiển thị các khả năng phù hợp để bạn chọn hoặc nhập thêm ký tự nhằm thu hẹp kết quả.

Ví dụ, tại dấu nhắc tương tác:

```
jshell> System.out.pr<Tab>
```

JShell có thể đưa ra các tên bắt đầu bằng `pr`, chẳng hạn `print`, `printf` và `println`. Đây là cách hoàn thành tên phương thức trên đối tượng `System.out`.

Hoàn thành mã phụ thuộc vào ngữ cảnh hiện tại, các import, classpath và những kiểu mà JShell có thể truy cập. Tab giúp nhập tên chính xác nhanh hơn; nó không tự sửa mọi lỗi cú pháp hoặc thêm thư viện chưa có trên classpath.

## 2. Xem tài liệu API ngay tại vị trí nhập

Sau khi nhấn Tab để xem hoặc hoàn thành một identifier, nhấn **Tab thêm một lần nữa**. Nếu có tài liệu phù hợp, JShell hiển thị documentation của identifier đó ngay trong phiên.

Quy trình thường dùng:

1. Nhập một phần tên kiểu hoặc phương thức.
2. Nhấn Tab để xem các tên phù hợp.
3. Nhấn Tab lần nữa để xem documentation nếu JShell có thể cung cấp.
4. Tiếp tục nhập đối số và đánh giá snippet.

Tài liệu không nhất thiết xuất hiện cho mọi tên. Kết quả phụ thuộc vào ngữ cảnh, symbol được chọn và tài liệu mà môi trường JDK có thể truy cập. Nếu có nhiều lựa chọn, hãy hoàn thành đúng identifier trước khi yêu cầu xem tài liệu.

Cách này hữu ích khi chưa nhớ chữ ký phương thức hoặc muốn kiểm tra API ngay trong lúc thử nghiệm. Nội dung documentation có thể cho biết mô tả và thông tin API liên quan mà không cần chuyển sang trình duyệt.

## 3. Gợi ý import cho identifier chưa được nhận diện

Khi nhập một identifier chưa được resolve, có thể dùng tổ hợp **Shift+Tab rồi nhấn `i`** để yêu cầu JShell đề xuất import.

JShell tìm các kiểu phù hợp dựa trên nội dung classpath hiện tại. Nếu có nhiều gợi ý, công cụ đánh số các lựa chọn. Nhập chữ số tương ứng để thêm import; nhấn `0` nếu không muốn thêm import nào.

Ví dụ, `Duration` thuộc package `java.time`, package này không nằm trong nhóm import mặc định thường dùng của JShell. Khi identifier chưa được nhận diện, thao tác gợi ý import có thể đề xuất `java.time.Duration` nếu kiểu đó có trên classpath.

Sau khi thêm import, có thể dùng tên ngắn:

```
Duration elapsed = Duration.ofSeconds(30);
elapsed.toMinutes()
```

Kết quả của biểu thức `elapsed.toMinutes()` là `0` vì 30 giây chưa đủ một phút. Ví dụ minh họa việc sử dụng kiểu sau khi import; thao tác gợi ý import được thực hiện bằng phím trong phiên tương tác, không phải bằng câu lệnh Java trong file.

Gợi ý import chỉ tìm kiểu có thể truy cập trong classpath. Nếu dependency không có sẵn, JShell không tự tải hoặc cài thư viện thay bạn.

## 4. Chuyển biểu thức thành khai báo biến hoặc phương thức

JShell có các phím tắt Shift+Tab giúp chuyển đoạn mã hiện tại thành một dạng khai báo khác:

| Phím | Khi dùng | Kết quả |
|---|---|---|
| Shift+Tab rồi `v` | Sau một biểu thức hoàn chỉnh | Chuyển biểu thức thành khai báo biến; kiểu được suy ra từ kiểu kết quả. |
| Shift+Tab rồi `m` | Sau biểu thức hoặc câu lệnh hoàn chỉnh | Chuyển nội dung thành khai báo phương thức; nếu là biểu thức, kiểu trả về được suy ra. |
| Shift+Tab rồi `i` | Sau một identifier chưa resolve | Đề xuất import có thể giải quyết identifier đó. |

Ví dụ, nhập biểu thức:

```
"hello".length()
```

Sau đó nhấn Shift+Tab, thả phím Shift và nhấn `v`. JShell chuyển biểu thức thành khai báo biến với kiểu dựa trên kiểu trả về `int`. Tên biến được tạo trong nội dung chuyển đổi có thể được chỉnh sửa trước khi đánh giá.

Với biểu thức:

```
"hello".toUpperCase()
```

Shift+Tab rồi `m` yêu cầu JShell chuyển biểu thức thành một khai báo phương thức. Kiểu trả về được suy ra từ kiểu `String` của biểu thức. Đây là cách nhanh để biến một thử nghiệm thành phương thức có thể gọi lại.

Các tổ hợp này được xử lý tại dấu nhắc tương tác. Chúng là thao tác bàn phím của JShell, không phải cú pháp để đưa vào file Java hoặc file JShell chạy tự động.

## 5. Chỉnh sửa snippet trong trình soạn thảo

Khi snippet đã dài hoặc cần chỉnh sửa nhiều dòng, dùng lệnh `/edit` để mở nội dung trong trình soạn thảo bên ngoài:

- `/edit` mở các snippet đang hoạt động mà bạn đã nhập hoặc nạp bằng `/open`.
- `/edit <id>` chỉnh sửa snippet theo ID.
- `/edit <name>` chỉnh sửa snippet theo tên.
- `/edit -all` mở tất cả snippet, gồm cả snippet lỗi, bị thay thế, đã drop và snippet khởi tạo.

Dùng `/list` để xem ID và nội dung trước khi chọn snippet cần chỉnh sửa.

### 5.1. Cấu hình trình soạn thảo

Lệnh `/set editor` cấu hình chương trình được dùng bởi `/edit`:

```
/set editor
/set editor <command>
/set editor -retain <command>
/set editor -wait <command>
```

`<command>` là lệnh hệ điều hành để khởi chạy trình soạn thảo. Có thể thêm đối số của editor sau tên chương trình. JShell thêm file tạm cần chỉnh sửa vào cuối danh sách đối số.

Nếu chưa cấu hình editor, JShell kiểm tra lần lượt các biến môi trường `JSHELLEDITOR`, `VISUAL` và `EDITOR`. Nếu không có cấu hình hoặc biến môi trường phù hợp, công cụ dùng editor đơn giản tích hợp sẵn.

Tùy chọn `-wait` hữu ích với editor khởi chạy cửa sổ riêng rồi trả quyền điều khiển ngay. Tùy chọn `-retain` giữ cấu hình cho các lần chạy JShell tiếp theo. Xem `/help /set editor` để biết cú pháp chi tiết.

## 6. Tra cứu lệnh và phím tắt bằng /help

`/help` là hệ thống trợ giúp tích hợp của JShell:

| Lệnh | Nội dung |
|---|---|
| `/help` | Danh sách lệnh và các chủ đề trợ giúp. |
| `/help <command>` | Tài liệu cho một lệnh cụ thể. |
| `/help shortcuts` | Các phím tắt hoàn thành mã và thao tác nhanh. |
| `/help keys` | Điều hướng, sửa dòng và thao tác lịch sử. |
| `/help id` | Cách nhận diện và sử dụng ID snippet. |
| `/help rerun` | Cách đánh giá lại snippet đã nhập. |

`/?` là dạng viết tắt của `/help`. Ví dụ, `/? /li` hiển thị trợ giúp cho lệnh khớp với tiền tố đó. Nếu có nhiều kết quả phù hợp, JShell có thể hiển thị nhiều phần trợ giúp.

Cần phân biệt hai dạng tra cứu:

- **Tài liệu lệnh JShell:** dùng `/help` để tìm cách dùng các lệnh điều khiển của công cụ.
- **Tài liệu Java API:** dùng hoàn thành identifier bằng Tab rồi nhấn Tab thêm lần nữa nếu documentation có sẵn.

## 7. Dùng lại snippet và tìm trong lịch sử

Khi thử nghiệm API, thường cần đánh giá lại đoạn mã vừa nhập hoặc quay lại một snippet cũ. JShell hỗ trợ:

- `/!`: chạy lại snippet gần nhất.
- `/<id>`: chạy lại snippet theo ID hoặc một khoảng ID.
- `/-<n>`: chạy lại snippet thứ n tính ngược từ lịch sử.
- `/history`: xem lịch sử nhập lệnh và snippet.
- **Ctrl+R**: tìm ngược trong lịch sử theo chuỗi ký tự.

Ví dụ, nếu vừa nhập một biểu thức kiểm tra và muốn đánh giá lại, dùng `/!`. Nếu muốn chạy lại một khai báo hoặc biểu thức cũ, xem ID bằng `/list` rồi dùng `/<id>`.

Các thao tác chạy lại sẽ thực thi snippet lần nữa. Nếu snippet có tác dụng phụ như ghi file, gửi yêu cầu mạng hoặc cập nhật dữ liệu, hãy cân nhắc trước khi chạy lại.

## 8. Quy trình thực hành trong một phiên

Một quy trình ngắn để khám phá API:

1. Khởi chạy JShell bằng `jshell --feedback concise`.
2. Nhập một biểu thức hoặc khai báo nhỏ để tạo ngữ cảnh.
3. Dùng Tab để hoàn thành tên biến, kiểu hoặc phương thức.
4. Nhấn Tab lần nữa để xem documentation nếu có.
5. Dùng Shift+Tab rồi `i` khi cần import cho identifier chưa resolve.
6. Dùng Shift+Tab rồi `v` hoặc `m` để chuyển biểu thức thành khai báo.
7. Dùng `/vars`, `/list` và `/history` để kiểm tra trạng thái và lịch sử.
8. Dùng `/edit` khi cần chỉnh sửa nhiều dòng, hoặc `/!` để chạy lại snippet gần nhất.

Ví dụ khởi tạo ngữ cảnh:

```
String greeting = "Hello, JShell";
greeting.toUpperCase()
/vars
/help shortcuts
```

Sau khi khai báo `greeting`, có thể gõ `greeting.toUp` rồi nhấn Tab để xem hoàn thành phương thức phù hợp. Nhấn Tab thêm lần nữa nếu muốn xem documentation. Kết quả biểu thức được lưu trong scratch variable, vì vậy nó cũng có thể được kiểm tra bằng `/vars`.

## 9. Lỗi thường gặp và cách tránh

1. **Nhấn Tab khi không ở dấu nhắc tương tác:** hoàn thành mã là thao tác bàn phím trong phiên JShell. File JShell chạy tự động không thể chờ người dùng nhấn Tab giữa lúc thực thi.
2. **Mong Tab luôn có một kết quả duy nhất:** một tiền tố có thể khớp nhiều identifier. Nhập thêm ký tự hoặc xem danh sách gợi ý.
3. **Mong lần nhấn Tab thứ hai luôn có documentation:** JShell chỉ hiển thị tài liệu khi có và phù hợp với identifier hiện tại.
4. **Nhầm /help với tài liệu API đầy đủ:** /help giải thích lệnh và phím tắt của JShell; documentation của Java API được yêu cầu thông qua thao tác hoàn thành identifier.
5. **Cho rằng gợi ý import tự tải dependency:** Shift+Tab rồi i chỉ đề xuất import từ nội dung classpath có thể truy cập.
6. **Dùng phím tắt IDE trong JShell:** JShell có bộ phím tắt riêng, đặc biệt Tab và các tổ hợp Shift+Tab. Xem `/help shortcuts` thay vì giả định phím tắt của IDE cũng áp dụng.
7. **Chỉnh sửa snippet nhưng không kiểm tra trạng thái:** sau khi dùng /edit, xem lại bằng /list và /vars để hiểu những khai báo đang có hiệu lực.
8. **Chạy lại snippet có tác dụng phụ:** /!, /<id> và /-<n> thực thi mã thêm một lần. Kiểm tra nội dung trước khi chạy lại.

## 10. Ghi nhớ

- Tab hoàn thành identifier Java, lệnh JShell và một số đối số lệnh.
- Nhấn Tab thêm lần nữa để xem documentation nếu có.
- Shift+Tab rồi `v` chuyển biểu thức thành khai báo biến; Shift+Tab rồi `m` chuyển thành khai báo phương thức.
- Shift+Tab rồi `i` đề xuất import cho identifier chưa resolve dựa trên classpath.
- `/edit` mở snippet trong editor; `/set editor` cấu hình editor.
- `/help` tra cứu lệnh và phím tắt; Tab lần hai hỗ trợ xem tài liệu Java API.
- `/!`, `/<id>`, `/-<n>` và Ctrl+R giúp lặp lại hoặc tìm snippet trong lịch sử.