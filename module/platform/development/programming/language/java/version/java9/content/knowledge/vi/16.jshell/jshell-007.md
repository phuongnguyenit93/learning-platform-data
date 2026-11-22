# Lưu, mở và phát lại nội dung phiên JShell

## 1. Vì sao cần lưu trạng thái phiên?

JShell là môi trường tương tác: bạn nhập khai báo, biểu thức và lệnh theo từng bước; các snippet hợp lệ được giữ trong trạng thái của phiên hiện tại. Khi đóng JShell, trạng thái làm việc trong bộ nhớ của phiên không tự trở thành một tệp dự án có thể mở lại.

Các lệnh lưu và khôi phục giúp bạn chủ động quản lý nội dung đã nhập:

- **/save** ghi mã nguồn của các snippet đang hoạt động ra tệp.
- **/open** đọc một tệp và xử lý nội dung của tệp như đầu vào JShell.
- **/reload** đặt lại trạng thái công cụ rồi phát lại lịch sử hợp lệ của phiên hiện tại.
- **/reset** xóa các khai báo đã nhập và khởi động lại execution state; startup code được chạy lại.

Điểm quan trọng là phân biệt một tệp lưu bền vững với lịch sử mà JShell còn giữ trong phiên đang chạy. Dùng /save khi cần lưu ra tệp để giữ lại; dùng /reload khi muốn dựng lại trạng thái từ lịch sử mà phiên hiện tại vẫn còn quản lý.

## 2. /save: lưu các snippet đang hoạt động

Cú pháp cơ bản:

~~~text
/save <file>
~~~

Lệnh này lưu mã nguồn của các snippet đang hoạt động vào tệp chỉ định. Tệp có thể dùng phần mở rộng tùy ý; ví dụ .jsh thường được dùng cho nội dung đầu vào JShell.

Ví dụ, nhập một biến và một phương thức:

~~~text
jshell> int base = 21;
base ==> 21

jshell> int doubled() {
   ...>     return base * 2;
   ...> }
|  created method doubled()
~~~

Lưu nội dung đang hoạt động:

~~~text
/save session.jsh
~~~

Tệp session.jsh chứa mã nguồn của các snippet đang hoạt động, chẳng hạn:

~~~java
int base = 21;
int doubled() {
    return base * 2;
}
~~~

/save lưu mã nguồn để có thể nạp lại; nó không lưu kết quả hiển thị trên màn hình như một bản ghi output hoàn chỉnh. Nếu muốn giữ cả lệnh đã nhập theo trình tự, hãy xem chế độ -history.

## 3. Các chế độ lưu khác nhau

JShell cung cấp các dạng /save phục vụ mục đích khác nhau:

| Cú pháp | Nội dung được lưu |
|---|---|
| /save <file> | Mã nguồn của snippet đang hoạt động |
| /save -all <file> | Mã nguồn của tất cả snippet, gồm snippet bị ghi đè, bị từ chối và startup code |
| /save -history <file> | Lịch sử tuần tự của các lệnh và snippet đã nhập kể từ khi JShell tool được khởi chạy |
| /save -start <file> | Các định nghĩa startup hiện tại |
| /save <id> <file> | Snippet được chỉ định bằng ID; có thể lưu một ID hoặc một dải ID |

Chọn chế độ theo mục tiêu:

- Dùng /save thông thường khi muốn tạo một tệp mã gọn để nạp lại các khai báo đang hoạt động.
- Dùng /save -all khi cần giữ lại cả những khai báo cũ đã bị ghi đè, bị từ chối hoặc startup code.
- Dùng /save -history khi cần bảo toàn trình tự tương tác, bao gồm các lệnh và snippet đã nhập.
- Dùng /save -start khi muốn xuất các định nghĩa startup hiện tại thành tệp riêng.
- Dùng /save với ID khi chỉ cần lưu một phần cụ thể của phiên.

Tệp lịch sử có thể chứa lệnh và giá trị bạn đã nhập trong phiên. Hãy kiểm tra nội dung trước khi chia sẻ, đặc biệt khi phiên có dữ liệu nội bộ, token, đường dẫn riêng hoặc thông tin nhạy cảm.

## 4. /open: nạp nội dung từ tệp vào phiên

Cú pháp:

~~~text
/open <file>
~~~

/open đọc tệp và xử lý nội dung bên trong như đầu vào của JShell. Nội dung có thể gồm khai báo Java, biểu thức và các lệnh JShell. Các snippet được đánh giá trong phiên hiện tại; những khai báo hợp lệ sẽ trở thành một phần trạng thái của phiên.

Ví dụ, sau khi lưu session.jsh ở phần trước:

~~~text
jshell> /open session.jsh
jshell> System.out.println(doubled());
42
~~~

Lệnh System.out.println gọi phương thức đã được nạp từ tệp và in kết quả 42.

Có thể truyền tên tệp tương đối hoặc đường dẫn hệ điều hành. Tên tệp tương đối được phân giải theo thư mục làm việc của tiến trình JShell. Vì /open thực thi nội dung như đầu vào, chỉ nạp tệp mà bạn tin cậy và đã kiểm tra.

JShell cũng hỗ trợ một số tên tệp dựng sẵn như DEFAULT, PRINTING, TOOLING và JAVASE. Chúng cung cấp các nhóm import hoặc phương thức tiện ích của JShell; khi cần biết nội dung và mục đích cụ thể, xem trợ giúp tích hợp bằng /help /open.

## 5. Quy trình lưu rồi mở lại một phiên

Một quy trình đơn giản để giữ các khai báo cần dùng:

1. Nhập các biến, phương thức và kiểu cần thiết.
2. Chạy /list để kiểm tra snippet đang hoạt động.
3. Chạy /save session.jsh để lưu mã nguồn đang hoạt động.
4. Khi cần dựng lại trạng thái, mở một phiên JShell mới hoặc đặt lại phiên hiện tại.
5. Chạy /open session.jsh để nạp lại các khai báo.
6. Gọi thử phương thức hoặc kiểm tra biến để xác nhận nội dung đã được nạp.

Ví dụ đầy đủ:

~~~text
jshell> int base = 21;
base ==> 21

jshell> int doubled() {
   ...>     return base * 2;
   ...> }
|  created method doubled()

jshell> /save session.jsh

jshell> /reset

jshell> /open session.jsh

jshell> System.out.println(doubled());
42
~~~

/reset xóa code đã nhập và khởi động lại execution state; startup code được chạy lại. Vì vậy, hãy lưu những khai báo cần giữ trước khi dùng /reset.

## 6. /reload: phát lại lịch sử của phiên hiện tại

Cú pháp:

~~~text
/reload
~~~

/reload đặt lại code và execution state của JShell tool, sau đó phát lại các snippet hợp lệ cùng các lệnh /drop theo đúng thứ tự chúng đã được nhập. Phạm vi lịch sử bắt đầu từ lúc JShell tool được khởi chạy hoặc từ lần /reset, /reload hay /env gần nhất.

Có thể dùng chế độ yên lặng:

~~~text
/reload -quiet
~~~

Với -quiet, JShell không hiển thị quá trình phát lại; lỗi phát sinh vẫn được hiển thị.

Một lựa chọn khác:

~~~text
/reload -restore
~~~

-restore yêu cầu JShell khôi phục lịch sử thuộc khoảng phiên trước đó, được giới hạn bởi những lần khởi chạy JShell tool, /reset, /reload hoặc /env. Nó hữu ích khi cần phục hồi trạng thái phiên trước đó trong phạm vi lịch sử mà JShell còn giữ.

Cần phân biệt /reload và /open:

| Lệnh | Nguồn dùng để dựng lại trạng thái |
|---|---|
| /reload | Lịch sử hợp lệ mà JShell tool còn giữ trong phiên |
| /reload -restore | Lịch sử của phiên trước đó trong phạm vi JShell còn quản lý |
| /open session.jsh | Nội dung của tệp được chỉ định |
| /reset | Xóa khai báo đã nhập và chạy lại startup code |

/reload không thay thế cho việc lưu tệp. Khi tiến trình JShell đã kết thúc và lịch sử trong bộ nhớ không còn, dùng tệp đã lưu bằng /save rồi /open để nạp lại nội dung.

## 7. Lưu và sử dụng startup definitions

JShell có thể chạy startup definitions khi khởi động. Muốn lưu các định nghĩa startup hiện tại:

~~~text
/save -start startup.jsh
~~~

Sau đó có thể chỉ định tệp startup khi khởi chạy JShell:

~~~bash
jshell --startup startup.jsh
~~~

Tùy chọn --startup dùng tệp được chỉ định làm bộ startup definitions thay thế cho startup definitions mặc định trong lần chạy đó.

Nếu cần khởi chạy mà không chạy startup definitions:

~~~bash
jshell --no-startup
~~~

Cần phân biệt ba loại nội dung:

- Snippet tương tác: các khai báo bạn nhập trong phiên.
- Startup definitions: nội dung được nạp tự động khi JShell khởi chạy.
- Tệp phiên: nội dung bạn lưu bằng /save và chủ động nạp lại bằng /open.

Không nên đưa các khai báo phụ thuộc môi trường cụ thể vào startup file dùng chung nếu những máy khác không có cùng class path, module path hoặc thư viện cần thiết.

## 8. Chọn chế độ lưu phù hợp

| Nhu cầu | Lệnh phù hợp | Lý do |
|---|---|---|
| Giữ các khai báo đang dùng để mở lại sau | /save session.jsh | Tệp gọn, chỉ gồm snippet đang hoạt động |
| Giữ cả snippet cũ, lỗi hoặc bị ghi đè | /save -all full-session.jsh | Bao gồm toàn bộ nguồn snippet theo chế độ -all |
| Giữ trình tự lệnh đã nhập | /save -history history.txt | Lưu lịch sử tuần tự của lệnh và snippet |
| Chia sẻ cấu hình startup | /save -start startup.jsh | Xuất các định nghĩa startup hiện tại |
| Lưu một snippet cụ thể | /save 5 selected.jsh | Chỉ lưu snippet có ID được chọn |
| Phát lại lịch sử hiện tại | /reload | Dựng lại trạng thái từ lịch sử còn trong JShell |
| Nạp nội dung từ tệp đã lưu | /open session.jsh | Đọc và đánh giá nội dung tệp trong phiên |

Nếu cần chia sẻ một ví dụ nhỏ, thường chỉ cần /save thông thường rồi kiểm tra tệp trước khi gửi. Nếu cần lưu lại quá trình thử nghiệm, dùng -history. Nếu cần tạo startup riêng cho nhóm, dùng -start và kiểm tra những dependency mà startup file yêu cầu.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| /open không tìm thấy tệp | Đường dẫn tương đối được tính từ thư mục làm việc khác | Kiểm tra thư mục hiện tại hoặc dùng đường dẫn đầy đủ |
| Nạp tệp nhưng một snippet báo lỗi | Tệp thiếu dependency, có khai báo không tương thích hoặc chứa lệnh không hợp lệ | Đọc lỗi tại snippet đó, bổ sung dependency hoặc sửa nội dung nguồn rồi nạp lại |
| /save không chứa khai báo cũ | /save mặc định chỉ lưu snippet đang hoạt động | Dùng /save -all nếu cần giữ cả snippet bị ghi đè, bị từ chối và startup |
| Tệp lưu không có output cũ | /save lưu mã nguồn, không phải bản ghi output | Thêm lệnh in kết quả vào tệp nếu muốn chạy và tạo output khi /open |
| /reload không khôi phục một phiên đã đóng từ lâu | Lịch sử mà /reload sử dụng thuộc phạm vi JShell tool còn quản lý | Dùng tệp đã lưu bằng /save và nạp lại bằng /open |
| /reset làm mất các khai báo đang làm | /reset xóa code đã nhập và khởi động lại execution state | Lưu trước bằng /save; sau đó dùng /open để nạp lại |
| Startup file chạy lỗi trên máy khác | Môi trường hoặc dependency không giống máy tạo tệp | Kiểm tra JDK, class path, module path và thư viện cần thiết |
| Tệp history chứa dữ liệu không nên chia sẻ | -history lưu lệnh và snippet đã nhập | Kiểm tra và loại bỏ dữ liệu nhạy cảm trước khi chia sẻ |

Khi /open gặp lỗi ở một snippet, hãy đọc thông báo cụ thể để xác định lỗi cú pháp hay dependency. Không nên giả định toàn bộ tệp đã được nạp thành công chỉ vì lệnh /open đã được gọi.

## 10. Trợ giúp tích hợp

Các lệnh có thể được tra cứu ngay trong JShell:

~~~text
/help /save
/help /open
/help /reload
/help /reset
~~~

Trợ giúp của phiên bản JDK đang chạy là nguồn tham chiếu trực tiếp cho cú pháp và tùy chọn. Nếu ví dụ ở tài liệu khác với kết quả trên máy, hãy kiểm tra phiên bản JDK và đọc trợ giúp tích hợp trước khi thay đổi quy trình.

Thói quen làm việc an toàn là lưu các snippet cần giữ bằng /save, kiểm tra tệp, rồi dùng /open để nạp lại khi cần. Dùng /reload cho lịch sử còn được JShell quản lý và /reset khi chủ động muốn bắt đầu lại execution state.