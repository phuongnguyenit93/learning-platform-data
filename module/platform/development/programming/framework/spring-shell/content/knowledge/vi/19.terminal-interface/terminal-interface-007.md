# Lịch sử lệnh, phím tắt và chỉnh sửa dòng với JLine

Khi làm việc với một CLI tương tác, người dùng thường chạy lại lệnh cũ, sửa một tham số, di chuyển con trỏ trong dòng hoặc tìm một lệnh đã nhập trước đó. Nếu phải xóa toàn bộ dòng và gõ lại mỗi lần, shell sẽ khó sử dụng khi command dài hoặc có nhiều option.

Spring Shell tích hợp JLine để đọc và chỉnh sửa đầu vào trong terminal. JLine cung cấp lịch sử lệnh, tìm kiếm lịch sử, các phím tắt điều hướng, thao tác xóa/cắt/dán và nhiều kiểu keymap. Spring Shell tự cấu hình `LineReader` và `History` cho shell; người dùng có thể tận dụng các thao tác mặc định và tùy chỉnh sâu hơn khi ứng dụng có yêu cầu riêng.

## 1. JLine đứng ở đâu trong Spring Shell?

Khi shell hiển thị prompt, JLine đọc từng phím, quản lý nội dung dòng đang nhập và chuyển dòng hoàn chỉnh cho Spring Shell xử lý. `LineReader` là thành phần trung tâm của JLine:

| Thành phần | Vai trò |
|---|---|
| `Terminal` | Giao tiếp với terminal, nhận phím và hiển thị ký tự |
| `LineReader` | Đọc dòng, quản lý con trỏ và thao tác chỉnh sửa |
| `History` | Lưu, duyệt và tìm kiếm những dòng đã nhập |
| `KeyMap` | Ánh xạ tổ hợp phím sang hành động |
| `Widget` | Hành động chỉnh sửa như xóa từ, di chuyển con trỏ hoặc chèn nội dung |

Trong Spring Shell 4.x, `JLineShellAutoConfiguration` tạo các bean `Terminal`, `LineReader`, `History`, parser, completer và highlighter. `JLineInputProvider` dùng `LineReader` để lấy dòng nhập và đưa vào shell. Vì vậy, lịch sử và thao tác sửa dòng là một phần của trải nghiệm REPL.

JLine được thiết kế để hoạt động với nhiều terminal và có các keymap tương tự GNU Readline. Một số phím có thể hoạt động khác nhau tùy terminal emulator, hệ điều hành hoặc cấu hình bàn phím.

## 2. Duyệt lịch sử bằng phím mũi tên

Sau khi nhập một command và nhấn Enter, dòng lệnh có thể được đưa vào history. Trong prompt, người dùng thường dùng:

| Phím | Hành động |
|---|---|
| Mũi tên lên (`↑`) | Lấy command trước đó trong lịch sử |
| Mũi tên xuống (`↓`) | Chuyển đến command mới hơn |
| `Ctrl+R` | Tìm ngược trong lịch sử theo chuỗi đang gõ |
| `Ctrl+S` | Tìm xuôi trong lịch sử nếu terminal hỗ trợ tổ hợp này |
| `Alt+<` | Chuyển đến mục đầu tiên trong lịch sử |
| `Alt+>` | Chuyển đến mục cuối cùng trong lịch sử |

Ví dụ, sau khi đã chạy:

~~~text
user create linh --email=linh@example.com --role=reader
user list --status=active
report export monthly --output=reports/monthly.csv
~~~

Nhấn `↑` một lần sẽ đưa dòng `report export` trở lại vùng nhập. Người dùng có thể sửa `monthly` thành `quarterly`, thay đổi đường dẫn output rồi nhấn Enter. Dòng cũ trong history vẫn được giữ như một lần thực thi trước đó.

`Ctrl+R` hữu ích khi lịch sử có nhiều lệnh. Gõ một phần tên command hoặc option để tìm lần xuất hiện gần nhất, sau đó tiếp tục tìm hoặc chấp nhận kết quả tùy key binding của JLine.

## 3. Lệnh history tích hợp

Ngoài thao tác bằng phím, Spring Shell cung cấp command `history` để hiển thị lịch sử các lệnh đã chạy. Trong Spring Shell 4.x, command này được đăng ký mặc định khi thuộc tính `spring.shell.command.history.enabled` không bị tắt.

Ví dụ:

~~~text
shell:> history
~~~

Lệnh này cho phép xem lại các dòng đã thực thi. API history của Spring Shell cũng hỗ trợ ghi các mục lịch sử ra file để dùng với command `script`.

Có hai cấu hình cần phân biệt:

| Property | Tác dụng |
|---|---|
| `spring.shell.history.enabled` | Bật hoặc tắt việc lưu lịch sử JLine |
| `spring.shell.command.history.enabled` | Bật hoặc tắt command `history` trong command registry |

Nếu chỉ tắt `spring.shell.command.history.enabled`, command `history` không còn xuất hiện trong danh sách trợ giúp, nhưng điều đó không đồng nghĩa với việc đã tắt lưu lịch sử. Nếu muốn ngừng ghi history xuống file, hãy cấu hình `spring.shell.history.enabled=false`.

## 4. Cấu hình nơi lưu và tên file lịch sử

Spring Shell có thể lưu history ra file để người dùng tiếp tục duyệt lệnh sau khi khởi động shell ở phiên mới. Có thể cấu hình việc lưu, tên file và vị trí cấu hình người dùng:

~~~yaml
spring:
  shell:
    history:
      enabled: true
      name: admin-shell-history.log
    command:
      history:
        enabled: true
    config:
      location: "{userconfig}"
~~~

`spring.shell.history.name` đặt tên file history. `spring.shell.config.location` điều chỉnh vị trí cấu hình người dùng; placeholder `{userconfig}` đại diện cho thư mục cấu hình dùng chung của người dùng. Nếu không cần tùy chỉnh, có thể giữ cấu hình mặc định của Spring Shell.

Để tắt lưu lịch sử:

~~~yaml
spring:
  shell:
    history:
      enabled: false
~~~

Để chỉ ẩn command `history` khỏi danh sách lệnh:

~~~yaml
spring:
  shell:
    command:
      history:
        enabled: false
~~~

Hãy chọn tên file và vị trí lưu phù hợp với cách triển khai ứng dụng. Nếu nhiều môi trường dùng chung một thư mục làm việc, nên cân nhắc cấu hình một vị trí riêng cho từng ứng dụng hoặc từng người dùng để tránh trộn lịch sử.

## 5. Lọc những dòng không nên đưa vào history

History tiện lợi nhưng cũng có thể lưu những dữ liệu không nên xuất hiện trong file văn bản, chẳng hạn token, mật khẩu hoặc giá trị bí mật truyền qua option.

JLine cung cấp một số cơ chế lọc:

- `HISTORY_IGNORE_DUPS`: bỏ qua những dòng trùng lặp theo quy tắc của history.
- `HISTORY_IGNORE_SPACE`: bỏ qua dòng bắt đầu bằng dấu cách.
- `HISTORY_IGNORE`: khai báo các pattern cần bỏ qua trong history.
- `HISTORY_REDUCE_BLANKS`: chuẩn hóa khoảng trắng trong dòng được lưu.

Ví dụ với JLine `LineReader`:

~~~java
import org.jline.reader.LineReader;

reader.setOpt(LineReader.Option.HISTORY_IGNORE_DUPS);
reader.setOpt(LineReader.Option.HISTORY_IGNORE_SPACE);
reader.setVariable(LineReader.HISTORY_IGNORE, "*--token=*:*--password=*");
~~~

`HISTORY_IGNORE_SPACE` chỉ hữu ích khi người dùng biết phải thêm dấu cách ở đầu dòng; đây không phải biện pháp bảo vệ bí mật. Pattern lọc cũng cần được kiểm tra với phiên bản JLine và cách viết command thực tế. Không nên dựa hoàn toàn vào history filter để bảo vệ thông tin xác thực.

Thiết kế command nên tránh nhận mật khẩu hoặc token trực tiếp trên dòng lệnh. Hãy dùng cơ chế nhập bí mật có che ký tự hoặc lấy thông tin từ kho lưu trữ bí mật của môi trường triển khai.

Không nhận pattern `HISTORY_IGNORE` tùy ý từ người dùng hoặc file cấu hình không đáng tin cậy. JLine từng có lỗ hổng tiêu thụ CPU khi xử lý một số pattern có biểu thức lồng nhau trong history; hãy dùng phiên bản JLine đã được vá và kiểm tra dependency thực tế của ứng dụng. Spring Shell 4.0.4 cập nhật JLine lên 3.30.17.

## 6. Các phím tắt chỉnh sửa dòng thường dùng

JLine hỗ trợ nhiều thao tác theo kiểu Emacs/Readline. Trong keymap Emacs mặc định, các phím thường gặp gồm:

| Phím | Hành động |
|---|---|
| `Ctrl+A` | Đưa con trỏ về đầu dòng |
| `Ctrl+E` | Đưa con trỏ về cuối dòng |
| `Ctrl+B` | Di chuyển con trỏ lùi một ký tự |
| `Ctrl+F` | Di chuyển con trỏ tiến một ký tự |
| `Alt+B` | Di chuyển lùi một từ |
| `Alt+F` | Di chuyển tiến một từ |
| `Ctrl+K` | Xóa phần từ con trỏ đến cuối dòng |
| `Ctrl+U` | Xóa phần từ đầu dòng đến con trỏ |
| `Ctrl+W` | Xóa từ đứng trước con trỏ |
| `Ctrl+Y` | Dán lại phần văn bản vừa cắt (yank) |
| `Ctrl+T` | Đổi chỗ hai ký tự cạnh con trỏ |
| `Ctrl+L` | Làm mới hoặc xóa nội dung hiển thị trên màn hình |

Ví dụ, người dùng đang nhập:

~~~text
report export monthly --output=reports/monthly.csv
~~~

Đặt con trỏ ở giữa dòng, dùng `Ctrl+W` để xóa từ đứng trước con trỏ hoặc `Alt+B` để lùi theo từ. Người dùng có thể sửa một phần command mà không phải xóa toàn bộ dòng.

Một số tổ hợp Alt được terminal gửi dưới dạng ký tự Escape rồi đến ký tự tiếp theo. Nếu `Alt+B` hoặc `Alt+F` không hoạt động, hãy kiểm tra cấu hình terminal hoặc thử phím mũi tên.

## 7. Hai kiểu chỉnh sửa: Emacs và Vi

JLine hỗ trợ hai kiểu keymap phổ biến:

| Kiểu | Đặc điểm |
|---|---|
| Emacs | Chỉnh sửa trực tiếp bằng các tổ hợp Ctrl/Alt; phù hợp với người quen GNU Readline |
| Vi | Có chế độ nhập và chế độ lệnh; thao tác điều hướng và chỉnh sửa gần với vi/vim |

Emacs là chế độ mặc định của `LineReader` trong JLine. Trong chế độ Vi:

- Nhấn `Esc` để chuyển sang command mode.
- Nhấn `i` để vào insert mode.
- Dùng `h`, `j`, `k`, `l` để di chuyển.
- Dùng `w` để tiến đến từ kế tiếp và `b` để lùi về từ trước.
- Dùng `d` để xóa, `y` để copy (yank) và `p` để dán (put).

Khi tạo `LineReader` độc lập bằng JLine, có thể chọn editing mode qua biến `LineReader.EDITING_MODE`:

~~~java
import org.jline.reader.LineReader;
import org.jline.reader.LineReaderBuilder;

LineReader reader = LineReaderBuilder.builder()
        .terminal(terminal)
        .variable(LineReader.EDITING_MODE, LineReader.VI)
        .build();
~~~

Để chọn Emacs một cách tường minh, dùng `LineReader.EMACS`. Trong Spring Shell, `LineReader` được tạo bởi auto-configuration; thay đổi editing mode trong ứng dụng Spring Shell cần tùy chỉnh reader đang được shell sử dụng, đồng thời giữ nguyên terminal, parser, completer, highlighter và history được Spring Shell cấu hình.

## 8. JLine dùng KeyMap và Widget như thế nào?

JLine không gắn cứng mỗi phím với một thao tác. `KeyMap` ánh xạ chuỗi phím thành một `Binding`, thường là tham chiếu đến `Widget`. Widget thực hiện hành động chỉnh sửa.

Một số widget có sẵn:

- `BEGINNING_OF_LINE`: chuyển con trỏ về đầu dòng.
- `END_OF_LINE`: chuyển con trỏ về cuối dòng.
- `UP_HISTORY` và `DOWN_HISTORY`: duyệt lịch sử.
- `BACKWARD_KILL_WORD`: xóa từ trước con trỏ.
- `KILL_WORD`: xóa từ sau con trỏ.
- `CLEAR_SCREEN`: làm mới màn hình.

Có thể truy cập keymap chính và gắn một widget có sẵn vào phím khác:

~~~java
import org.jline.keymap.Binding;
import org.jline.keymap.KeyMap;
import org.jline.reader.LineReader;
import org.jline.reader.Reference;

KeyMap<Binding> mainKeyMap =
        reader.getKeyMaps().get(LineReader.MAIN);

mainKeyMap.bind(
        new Reference(LineReader.BEGINNING_OF_LINE),
        KeyMap.ctrl('A')
);
~~~

Ví dụ trên minh họa API JLine. Trong thực tế, `Ctrl+A` thường đã được gắn với thao tác về đầu dòng ở Emacs mode, vì vậy chỉ cần thêm binding khi muốn đổi hoặc khôi phục hành vi đã chọn.

## 9. Tạo phím tắt riêng bằng Widget

Nếu ứng dụng cần một thao tác riêng, có thể tạo `Widget`, đăng ký nó với `LineReader` rồi gắn vào `KeyMap`.

Ví dụ, chèn ngày hiện tại tại vị trí con trỏ:

~~~java
import java.time.LocalDate;
import org.jline.keymap.Binding;
import org.jline.keymap.KeyMap;
import org.jline.reader.LineReader;
import org.jline.reader.Widget;

Widget insertDate = () -> {
    reader.getBuffer().write(LocalDate.now().toString());
    return true;
};

reader.getWidgets().put("insert-date", insertDate);

KeyMap<Binding> mainKeyMap =
        reader.getKeyMaps().get(LineReader.MAIN);
mainKeyMap.bind(insertDate, KeyMap.alt('d'));
~~~

Sau khi binding được cài đặt, nhấn `Alt+D` sẽ chèn ngày hiện tại vào dòng đang soạn. Ví dụ này dành cho một JLine `LineReader` mà ứng dụng có quyền cấu hình.

Khi tùy chỉnh key binding, cần:

- Chọn phím ít xung đột với binding mặc định.
- Giữ nguyên những thao tác phổ biến như Enter, Ctrl+C và điều hướng.
- Công bố phím tắt mới trong tài liệu hoặc trợ giúp của ứng dụng.
- Kiểm thử trong những terminal emulator mà người dùng thực tế sử dụng.

## 10. History expansion và tìm kiếm lệnh

JLine hỗ trợ history expansion theo kiểu Bash. Một số biểu thức thường gặp:

| Biểu thức | Ý nghĩa |
|---|---|
| `!!` | Tham chiếu command gần nhất |
| `!n` | Tham chiếu mục history có số thứ tự `n` |
| `!-n` | Tham chiếu command cách đây `n` mục |
| `!string` | Tìm command gần nhất bắt đầu bằng chuỗi |
| `^old^new^` | Thay chuỗi `old` bằng `new` trong command trước theo cú pháp expansion |

History expansion có thể hữu ích khi chạy lại command dài và chỉ thay đổi một phần nhỏ. Tuy nhiên, ký tự `!` cũng thường xuất hiện trong biểu thức hoặc dữ liệu đầu vào. Đường dẫn Windows chứa dấu gạch chéo ngược cũng có thể bị ảnh hưởng bởi cách xử lý escape.

JLine có tùy chọn `DISABLE_EVENT_EXPANSION` để tắt history expansion và diễn giải escape:

~~~java
reader.setOpt(LineReader.Option.DISABLE_EVENT_EXPANSION);
~~~

Nếu muốn bật lại, bỏ tùy chọn:

~~~java
reader.unsetOpt(LineReader.Option.DISABLE_EVENT_EXPANSION);
~~~

Hãy kiểm tra hành vi thực tế trong shell của ứng dụng trước khi hướng dẫn người dùng dựa vào `!!` hoặc `!n`, vì cấu hình parser và expander có thể thay đổi cách xử lý đầu vào.

## 11. Phân biệt history, script và command history

Ba khái niệm có liên quan nhưng không giống nhau:

| Thành phần | Vai trò |
|---|---|
| JLine `History` | Lưu các dòng người dùng đã nhập trong phiên tương tác và hỗ trợ duyệt/tìm kiếm |
| Spring Shell command `history` | Hiển thị lịch sử và có thể ghi ra file để dùng lại |
| Spring Shell script | Đọc file chứa các command và thực thi theo thứ tự |

History ghi lại những dòng đã nhập; script là nguồn đầu vào được chuẩn bị trước để chạy một chuỗi command. Nếu cần tự động hóa lặp lại, hãy lưu các bước ổn định vào script thay vì phụ thuộc vào lịch sử tương tác của một người dùng.

Không nên coi file history là file script an toàn để chạy lại. History có thể chứa command thử nghiệm, tham số cũ hoặc dữ liệu nhạy cảm. Hãy xem lại nội dung trước khi chuyển nó thành script.

## 12. Tùy chỉnh LineReader trong Spring Shell

Spring Shell 4.x tự tạo `LineReader` thông qua `JLineShellAutoConfiguration`. Bean này được cấu hình với:

- `Terminal` để đọc và hiển thị dữ liệu.
- `Parser` để xử lý dòng nhập.
- `CommandCompleter` để hoàn thành command và option.
- `CommandHighlighter` để tô sáng dòng nhập.
- `History` để lưu và duyệt command.

Nếu ứng dụng cần thay đổi keymap hoặc editing mode, cần tùy chỉnh đúng `LineReader` được `JLineInputProvider` sử dụng. Khi thay thế bean mặc định, hãy giữ các thành phần parser, completer, highlighter, terminal và history của Spring Shell. Nếu tạo một reader độc lập nhưng shell vẫn dùng reader mặc định, phím tắt mới sẽ không tác động đến prompt.

Với nhu cầu đơn giản, ưu tiên dùng các phím tắt có sẵn của JLine và cấu hình history. Chỉ thay thế hoặc tùy chỉnh sâu `LineReader` khi thực sự cần một bộ keymap riêng.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nhấn `↑` nhưng không thấy command cũ | History bị tắt hoặc terminal không gửi đúng phím mũi tên | Kiểm tra `spring.shell.history.enabled` và terminal emulator |
| Lịch sử mất sau khi khởi động lại | History chỉ được giữ trong bộ nhớ hoặc không ghi được file | Kiểm tra cấu hình history, tên file và quyền ghi thư mục |
| `history` không xuất hiện trong `help` | Built-in command bị tắt | Kiểm tra `spring.shell.command.history.enabled` |
| Command chứa token xuất hiện trong history | Bí mật được truyền trực tiếp trên dòng lệnh | Dùng prompt có che ký tự hoặc kho bí mật; cấu hình lọc history bổ sung |
| `Ctrl+R` không hoạt động | Terminal hoặc keymap đang dùng không chuyển đúng tổ hợp phím | Thử terminal khác hoặc kiểm tra keymap `SEARCH` |
| `Alt+B`/`Alt+F` không hoạt động | Terminal gửi Escape sequence khác hoặc Alt bị hệ điều hành chiếm | Dùng phím mũi tên hoặc cấu hình terminal |
| Phím tắt mới không có tác dụng trong Spring Shell | Binding được gắn vào một `LineReader` khác với reader của shell | Tùy chỉnh reader được `JLineInputProvider` sử dụng |
| Phím tắt mới làm hỏng thao tác cũ | Ghi đè key binding quan trọng | Chọn tổ hợp khác và kiểm tra toàn bộ thao tác cơ bản |
| Chỉnh sửa dòng lỗi trong IDE | Console của IDE không hỗ trợ đầy đủ terminal mode | Chạy ứng dụng trong terminal thực hoặc cấu hình terminal ngoài |
| Tab, history và key binding đều không hoạt động | Terminal chưa ở raw mode hoặc không khởi tạo được terminal thật | Kiểm tra terminal provider và chế độ terminal |

## 14. Checklist kiểm thử trải nghiệm dòng lệnh

Trước khi phát hành shell, kiểm tra:

1. Nhập vài command rồi dùng `↑` và `↓` để duyệt lại.
2. Dùng `Ctrl+R` để tìm một command cũ theo chuỗi.
3. Đưa con trỏ vào giữa command và sửa argument hoặc option.
4. Dùng các thao tác xóa từ, xóa phần cuối dòng và dán lại nội dung đã cắt.
5. Thoát ứng dụng, khởi động lại và xác nhận history còn được lưu nếu tính năng này bật.
6. Xác nhận command `history` bật/tắt độc lập với việc lưu file history.
7. Kiểm tra các dòng chứa token hoặc mật khẩu không bị lưu ngoài ý muốn.
8. Kiểm tra phím tắt trong Windows Terminal, terminal Linux/macOS và console IDE nếu các môi trường đó được hỗ trợ.
9. Nếu có key binding riêng, xác nhận nó không ghi đè Enter, Ctrl+C, Ctrl+D hoặc các phím điều hướng thiết yếu.

## 15. Bài tập thực hành

Tạo một CLI quản lý tài khoản với các command:

- `user list`: liệt kê tài khoản.
- `user show <username>`: hiển thị chi tiết một tài khoản.
- `user disable <username>`: vô hiệu hóa tài khoản.

Thực hiện:

1. Bật lưu history và đặt tên file `account-cli-history.log`.
2. Chạy ba command trên theo nhiều thứ tự khác nhau.
3. Dùng `↑` để gọi lại `user disable`, sửa username rồi thực thi.
4. Dùng `Ctrl+R` để tìm command `user show`.
5. Dùng `Ctrl+A`, `Ctrl+E`, `Alt+B` và `Alt+F` để sửa dòng dài.
6. Mở command `history` và xem lại những dòng đã nhập.
7. Khởi động lại ứng dụng và kiểm tra history có được nạp lại không.
8. Tạo một key binding JLine riêng để chèn ngày hiện tại vào dòng nhập.
9. Thử tắt command `history` nhưng giữ lưu history, sau đó thử tắt lưu history.

Sau bài tập, hãy giải thích được vai trò của `LineReader`, `History`, `KeyMap` và `Widget`; đồng thời phân biệt thao tác duyệt history với việc chạy một script.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 – Exit và lịch sử JLine](https://docs.spring.io/spring-shell/reference/commands/builtin/exit.html)
- [Spring Shell 4.0.3 API – JLineShellAutoConfiguration](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/JLineShellAutoConfiguration.html)
- [Spring Shell 4.0.3 API – SpringShellProperties](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/SpringShellProperties.html)
- [Spring Shell 4.0.3 API – SpringShellProperties.History](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/SpringShellProperties.History.html)
- [Spring Shell 4.0.4 Release Notes – JLine 3.30.17](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4)
- [JLine 3 – History](https://jline.org/versions/3.x/docs/history/)
- [JLine 3 – Line Reading](https://jline.org/versions/3.x/docs/line-reader/)
- [JLine – Key Bindings and Widgets](https://jline.github.io/docs/advanced/key-bindings/)
- [JLine 3 – Troubleshooting](https://jline.org/versions/3.x/docs/troubleshooting/)
- [JLine CVE-2026-77420 – HISTORY_IGNORE pattern processing](https://bugzilla.redhat.com/show_bug.cgi?id=2539624)
