# Thứ tự thực thi các dòng và quy tắc chú thích

## 1. Script trong Spring Shell là gì?

Script là một tệp văn bản chứa nhiều command Spring Shell. Thay vì nhập từng lệnh trong terminal, người dùng chuẩn bị trước danh sách command rồi yêu cầu shell đọc và thực thi tệp đó. Cách này phù hợp với các công việc lặp lại như khởi tạo dữ liệu, kiểm tra trạng thái, cấu hình môi trường hoặc chạy một quy trình bảo trì.

Một script Spring Shell 4.x có quy tắc cơ bản:

- Mỗi dòng chứa một command.
- Các command được thực thi theo thứ tự xuất hiện trong tệp, từ trên xuống dưới.
- Một dòng bắt đầu bằng `//` là dòng chú thích.
- Có thể dùng dòng trống để tách các nhóm command trong phiên bản đã sửa lỗi xử lý dòng trống.

Ví dụ:

~~~text
// Chuẩn bị dữ liệu người dùng
user create --email=linh@example.com --role=ADMIN
user create --email=nam@example.com --role=USER

// Kiểm tra dữ liệu vừa tạo
user list
user show --id=1001
~~~

Shell đọc các dòng theo thứ tự. Vì vậy, command tạo người dùng chạy trước command liệt kê và xem chi tiết. Nếu một command sau phụ thuộc vào kết quả của command trước, thứ tự trong tệp phải thể hiện đúng quan hệ đó.

## 2. Hai cách chạy tệp script

Spring Shell 4.x hỗ trợ hai cách thường gặp để thực thi các command trong tệp. Hai cách này dùng runner khác nhau và phù hợp với ngữ cảnh khác nhau.

| Cách chạy | Ngữ cảnh | Cú pháp |
|---|---|---|
| Built-in command `script` | Người dùng đang ở phiên shell tương tác | `script --file <đường-dẫn>` |
| Script qua `NonInteractiveShellRunner` | Chạy tự động từ terminal, scheduler hoặc CI | `java -jar ... @<đường-dẫn>` với interactive mode tắt |

Không nhầm command built-in `script` với tiền tố `@` của non-interactive runner. Cả hai đều nhận tệp chứa command, nhưng cách gọi và vòng đời tiến trình khác nhau.

## 3. Chạy script từ phiên tương tác

Khi ứng dụng đã khởi động và hiển thị prompt, dùng command built-in `script` với option `--file`.

Ví dụ tệp nằm tại đường dẫn tuyệt đối:

~~~text
shell:>script --file /opt/admin/scripts/maintenance.txt
~~~

Trên Windows, có thể dùng đường dẫn tuyệt đối của hệ thống tệp:

~~~text
shell:>script --file C:/admin/scripts/maintenance.txt
~~~

Trong Spring Shell 4.0.4, option `--file` cũng nhận Spring resource reference, ví dụ `classpath:` hoặc `file:`:

~~~text
shell:>script --file classpath:scripts/maintenance.txt
shell:>script --file file:/opt/admin/scripts/maintenance.txt
~~~

Đường dẫn `classpath:` hữu ích khi tệp script được đóng gói cùng ứng dụng trong resources. Đường dẫn `file:` trỏ đến tệp bên ngoài. Với tệp nằm trong thư mục làm việc hoặc thư mục do người vận hành quản lý, hãy chọn đường dẫn rõ ràng để tránh phụ thuộc vào working directory hiện tại.

Khi command `script` hoàn tất, người dùng vẫn ở trong phiên shell tương tác và có thể tiếp tục nhập command khác.

## 4. Chạy script ở chế độ non-interactive

Khi muốn chạy tệp command từ script hệ điều hành hoặc pipeline CI, dùng `NonInteractiveShellRunner`. Spring Shell 4.x mặc định bật interactive mode, vì vậy cần đặt:

~~~properties
spring.shell.interactive.enabled=false
~~~

Sau đó truyền tên tệp có tiền tố `@` cho tiến trình:

~~~bash
java -jar target/admin-cli.jar @/opt/admin/scripts/maintenance.txt
~~~

Nếu tệp ở thư mục làm việc hiện tại:

~~~bash
java -jar target/admin-cli.jar @maintenance.txt
~~~

`NonInteractiveShellRunner` đọc các command trong tệp, thực thi rồi kết thúc ứng dụng. Cách này phù hợp khi không cần prompt hoặc nhập thêm lệnh sau khi script hoàn tất.

Có thể đặt property trong `application.properties` hoặc truyền qua biến môi trường:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false java -jar target/admin-cli.jar @maintenance.txt
~~~

Nếu chỉ truyền `@maintenance.txt` nhưng ứng dụng vẫn chạy ở interactive mode, hãy kiểm tra cấu hình `spring.shell.interactive.enabled`. Spring Shell 4.x không tự chuyển sang non-interactive chỉ vì tiến trình có command-line arguments.

## 5. Thứ tự thực thi và sự phụ thuộc giữa các command

Tệp script được đọc từ đầu đến cuối. Dòng lệnh ở vị trí trước được xử lý trước dòng ở vị trí sau. Ví dụ:

~~~text
// Bước 1: tạo nhóm người dùng
group create --name=operators

// Bước 2: tạo tài khoản
user create --email=ops@example.com --role=OPERATOR

// Bước 3: thêm tài khoản vào nhóm
group member add --group=operators --user=ops@example.com

// Bước 4: kiểm tra kết quả
group member list --group=operators
~~~

Trình tự này thể hiện quan hệ phụ thuộc: nhóm phải tồn tại trước khi thêm thành viên; tài khoản phải tồn tại trước khi liên kết với nhóm. Nếu đảo vị trí các dòng, command có thể thất bại vì tài nguyên chưa được tạo.

Một số nguyên tắc tổ chức:

- Đặt bước chuẩn bị trước bước sử dụng tài nguyên.
- Đặt bước kiểm tra sau bước thay đổi để xác nhận kết quả.
- Gom các command cùng mục đích thành từng đoạn, dùng dòng chú thích để đặt tiêu đề.
- Không dựa vào việc các command được chạy song song; script được mô tả là thực thi theo thứ tự dòng.
- Với command có tác dụng phụ, cân nhắc khả năng chạy lại và tránh tạo dữ liệu trùng.

Script chỉ sắp xếp thứ tự gọi command. Nó không tự tạo một transaction chung cho toàn bộ tệp. Nếu command thứ ba thất bại sau khi hai command đầu đã cập nhật database, các thay đổi trước đó không tự động được rollback chỉ vì script có lỗi.

## 6. Quy tắc chú thích bằng `//`

Trong tệp script của built-in command `script`, một dòng được xem là chú thích khi bắt đầu bằng hai dấu gạch chéo `//`.

Ví dụ:

~~~text
// Tạo dữ liệu nền
catalog seed --source=default

// Đồng bộ dữ liệu
catalog sync --target=staging
~~~

Các dòng chú thích giúp chia script thành các phần dễ đọc. Chúng không phải command và không được gửi đến command parser để thực thi.

### Đặt chú thích trên dòng riêng

Tài liệu Spring Shell mô tả chú thích bằng cách bắt đầu một dòng với `//`. Vì vậy, hãy đặt chú thích trên dòng riêng:

~~~text
// Xuất báo cáo sau khi đồng bộ
report export --format=json
~~~

Không dựa vào cú pháp chú thích ở cuối command như:

~~~text
report export --format=json // xuất báo cáo
~~~

Đây không phải dạng chú thích được tài liệu script 4.x xác nhận. Parser có thể coi phần sau command là token đầu vào và khiến command lỗi.

### Không thay `//` bằng `#`

Tài liệu Spring Shell 4.x chỉ mô tả dòng chú thích bắt đầu bằng `//`. Không mặc định rằng cú pháp `#` của Bash, PowerShell hoặc YAML cũng là chú thích hợp lệ trong tệp command Spring Shell.

~~~text
// Đây là chú thích theo cú pháp Spring Shell
user list

# Không dùng cú pháp này làm chú thích Spring Shell nếu chưa tự xử lý riêng
report run
~~~

Nếu cần dùng cùng một tệp cho nhiều công cụ, hãy thống nhất cú pháp chú thích mà mọi công cụ đều hỗ trợ hoặc chuyển đổi tệp trước khi đưa cho Spring Shell.

## 7. Dòng trống và phiên bản Spring Shell

Dòng trống có thể được dùng để phân tách các nhóm command, giúp script dễ đọc hơn. Tuy nhiên, Spring Shell 4.0.1 có lỗi khiến dòng trống trong script có thể hiển thị danh sách command thay vì được bỏ qua.

Spring Shell 4.0.2 đã sửa lỗi liên quan đến dòng trống và cả lỗi khiến script dừng khi gặp dòng chú thích. Vì vậy, khi dùng comment và blank line trong script, nên sử dụng Spring Shell 4.0.2 trở lên; ví dụ trong bài được kiểm tra theo nhánh 4.0.4.

Ví dụ bố cục:

~~~text
// Phần 1: kiểm tra môi trường
system status
database ping

// Phần 2: cập nhật dữ liệu
catalog sync --target=staging
cache clear

// Phần 3: xác nhận
catalog status
~~~

Nếu ứng dụng đang chạy 4.0.0 hoặc 4.0.1, hãy nâng cấp lên bản sửa lỗi phù hợp trước khi dựa vào dòng chú thích hoặc dòng trống để tổ chức script. Không nên xóa các dòng chú thích để né lỗi nếu người vận hành cần chúng để hiểu quy trình.

## 8. Mỗi dòng một command và cách trình bày command dài

Tài liệu Spring Shell 4.x mô tả tệp script có một command trên mỗi dòng. Hãy giữ mỗi command trên một dòng vật lý để người đọc dễ xác định vị trí lỗi và thứ tự thực thi.

Ví dụ:

~~~text
report export --type=monthly --from=2026-01-01 --to=2026-01-31 --format=json
~~~

Nếu command dài, có thể sắp xếp option theo thứ tự dễ đọc và dùng tên option có ý nghĩa. Không tự giả định dấu `\` ở cuối dòng có chức năng nối dòng trong script Spring Shell 4.x; cú pháp continuation có trong tài liệu cũ của nhánh 3.x nhưng không được mô tả trong quy tắc script 4.x hiện hành.

Giá trị chứa khoảng trắng cần được đặt trong dấu nháy theo cú pháp parser:

~~~text
user create --display-name="Nguyen Van An" --email=an@example.com
~~~

Không xuống dòng giữa tên option và giá trị. Hãy kiểm tra `help <command>` để xác nhận cú pháp của command trước khi đưa vào script dùng chung.

## 9. Script built-in và `@file` có gì khác nhau?

Hai cơ chế cùng dùng tệp văn bản nhưng có mục đích khác nhau:

| Tiêu chí | `script --file` | `@file` |
|---|---|---|
| Cách gọi | Nhập trong prompt interactive | Truyền vào tiến trình khi khởi động |
| Runner | Phiên interactive đang chạy | `NonInteractiveShellRunner` |
| Kết thúc | Quay lại prompt sau khi chạy script | Tiến trình kết thúc sau khi chạy script |
| Đường dẫn | Absolute path hoặc Spring resource như `classpath:` và `file:` | Tên/đường dẫn tệp đứng sau tiền tố `@` |
| Trường hợp dùng | Người vận hành chạy một nhóm command rồi tiếp tục làm việc | CI, scheduler hoặc tự động hóa không cần prompt |

Đối với `script --file`, tài liệu 4.0.4 nêu rõ cú pháp dòng chú thích `//` và mỗi dòng một command. API `NonInteractiveShellRunner` mô tả việc chạy một script bằng tiền tố `@`; nếu cần dựa vào hành vi cụ thể của comment, blank line hoặc lỗi giữa chừng trong `@file`, hãy kiểm thử bằng đúng phiên bản runner đang triển khai thay vì suy rộng các chi tiết chưa được API runner mô tả riêng.

## 10. Xử lý lỗi trong một chuỗi command

Thứ tự dòng không đồng nghĩa với tính nguyên tử. Mỗi command có thể đọc hoặc cập nhật trạng thái riêng. Nếu một command lỗi, những thay đổi đã commit từ command trước không tự động được hoàn tác.

Tài liệu script cam kết thứ tự thực thi, nhưng không mô tả đầy đủ một chính sách chung rằng mọi runner và mọi loại lỗi đều tiếp tục hay dừng ở dòng lỗi. Vì vậy, với quy trình quan trọng, hãy xác định hành vi lỗi bằng kiểm thử tích hợp trên phiên bản Spring Shell cụ thể.

Một số cách giảm rủi ro:

- Chia quy trình dài thành các script nhỏ theo giai đoạn.
- Thêm command kiểm tra trạng thái trước và sau bước cập nhật.
- Thiết kế command có thể chạy lại an toàn khi phù hợp (idempotent).
- Ghi lại ID hoặc kết quả của từng bước để người vận hành biết đã hoàn tất đến đâu.
- Với pipeline, kiểm tra exit code của tiến trình và dừng pipeline khi bước bắt buộc thất bại.
- Không giả định toàn bộ file script nằm trong một transaction database.

Nếu một command có thể thực hiện thao tác không thể đảo ngược, chẳng hạn gửi thông báo hoặc xóa dữ liệu, hãy đặt bước xác nhận và kiểm tra điều kiện trước khi gọi command đó.

## 11. Ví dụ script hoàn chỉnh

Tạo tệp `release-check.commands`:

~~~text
// 1. Xác nhận hệ thống sẵn sàng
system status
database ping

// 2. Kiểm tra phiên bản cần phát hành
release show --id=42
release validate --id=42

// 3. Xuất thông tin phục vụ lưu trữ
release export --id=42 --format=json

// 4. Xác nhận trạng thái cuối
release status --id=42
~~~

Chạy từ phiên tương tác:

~~~text
shell:>script --file /opt/admin/scripts/release-check.commands
~~~

Hoặc cấu hình non-interactive và chạy từ terminal:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar target/admin-cli.jar @/opt/admin/scripts/release-check.commands
~~~

Các command được gọi theo thứ tự từ bước 1 đến bước 4. Nếu command `release validate` phụ thuộc vào kết quả `release show`, việc đặt nó sau command đọc thông tin giúp quy trình dễ theo dõi. Nếu bước validate thất bại, hãy xác nhận chính sách dừng/tiếp tục của runner bằng kiểm thử trước khi dùng script trong môi trường thật.

## 12. Kiểm thử thứ tự và chú thích

Một script nên được kiểm thử như một phần của quy trình tự động hóa. Có thể tạo command test ghi lại thứ tự gọi hoặc dùng mock service để xác nhận các thao tác xảy ra đúng trình tự.

Các trường hợp nên kiểm tra:

1. Hai command liên tiếp được gọi theo thứ tự xuất hiện trong tệp.
2. Dòng chú thích bắt đầu bằng `//` không gọi command.
3. Dòng trống không tạo command ngoài ý muốn trên phiên bản đã sửa lỗi.
4. Command có option chứa khoảng trắng được parse đúng khi đặt trong dấu nháy.
5. Tệp script được tìm thấy bằng absolute path, `file:` và `classpath:` khi dùng built-in `script`.
6. Tệp `@file` được chạy khi `spring.shell.interactive.enabled=false`.
7. Lỗi ở một command tạo output và exit code đúng theo chính sách của ứng dụng.
8. Chạy lại script không tạo dữ liệu trùng hoặc tác dụng phụ ngoài dự kiến.

Spring Shell 4.0.2 đã sửa các lỗi script dừng tại dòng comment và xử lý sai dòng trống. Nếu kiểm thử các trường hợp này thất bại, hãy kiểm tra phiên bản dependency thực tế trong runtime, không chỉ phiên bản khai báo trong file build.

## Kết luận

Script Spring Shell 4.x thực thi các command theo thứ tự dòng trong tệp. Với built-in command `script`, mỗi dòng chứa một command và dòng chú thích bắt đầu bằng `//`; Spring Shell 4.0.2 trở lên đã sửa các lỗi xử lý comment và dòng trống của những bản 4.0 đầu tiên. Người dùng có thể chạy tệp từ prompt bằng `script --file` hoặc chạy tự động bằng `NonInteractiveShellRunner` với tiền tố `@`. Hãy giữ cú pháp rõ ràng, kiểm thử hành vi khi có lỗi và nhớ rằng thứ tự command không tạo transaction chung cho toàn bộ script.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 – Script command](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Spring Shell 4.0.4 – NonInteractiveShellRunner API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Spring Shell 4.0.4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell 4.x – v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell – Releases and fixes in 4.0.2 and 4.0.4](https://github.com/spring-projects/spring-shell/releases)
