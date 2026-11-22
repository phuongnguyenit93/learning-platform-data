# Debug local ứng dụng Java

## Mục tiêu

Sau bài này, bạn có thể thiết lập phiên debug local cho ứng dụng Java; hiểu vai trò của source code, bytecode, debug information và JVM; đặt breakpoint; chạy từng bước bằng Step Into, Step Over và Step Out; đọc biến local, field, call stack và thread; dừng tại exception; dùng debugger của IDE hoặc jdb; attach vào JVM local đã bật JDWP; tái hiện và sửa lỗi logic; và xử lý các vấn đề thường gặp khi debug.

## 1. Debug local là gì?

**Debug local** là quá trình chạy ứng dụng Java trên máy phát triển dưới sự điều khiển của debugger. Debugger cho phép tạm dừng chương trình tại một vị trí, kiểm tra trạng thái JVM, xem giá trị biến và theo dõi cách chương trình đi qua các nhánh lệnh.

Thay vì chỉ nhìn output cuối cùng hoặc thêm nhiều câu lệnh System.out.println, bạn có thể dừng ngay trước hoặc sau một dòng đáng nghi để kiểm tra dữ liệu và luồng thực thi.

Debug local thường được dùng để:

- Tìm lỗi logic như sai điều kiện, sai phép tính hoặc xử lý boundary.
- Tìm nguyên nhân NullPointerException, IndexOutOfBoundsException và exception khác.
- Kiểm tra giá trị input, biến local, field và object state.
- Theo dõi call stack để biết method nào gọi tới đoạn code hiện tại.
- Quan sát vòng lặp, nhánh if/switch và luồng xử lý.
- Kiểm tra trạng thái nhiều thread khi có race condition hoặc deadlock.
- Xác nhận một bản sửa lỗi đã thay đổi đúng hành vi.

Debug local phù hợp khi có thể tái hiện vấn đề bằng source code, cấu hình và dữ liệu trên máy phát triển. Nếu lỗi chỉ xuất hiện trong production do tải, dữ liệu, thời gian hoặc môi trường khác biệt, hãy kết hợp debugger với log, metrics, JFR và dữ liệu chẩn đoán phù hợp.

## 2. Debugger hoạt động như thế nào?

Một phiên debug Java có ba thành phần chính:

- **Debuggee:** JVM đang chạy ứng dụng cần kiểm tra.
- **Debugger:** IDE hoặc công cụ như jdb điều khiển phiên debug và hiển thị trạng thái chương trình.
- **Debug interface/protocol:** cơ chế để debugger yêu cầu JVM đặt breakpoint, tạm dừng thread, đọc biến và tiếp tục thực thi.

Trong Java Platform Debugger Architecture (JPDA):

- **JDI (Java Debug Interface)** là API cấp cao mà debugger sử dụng để điều khiển và quan sát JVM.
- **JDWP (Java Debug Wire Protocol)** là giao thức trao đổi lệnh và phản hồi giữa debugger và JVM đích.
- **JVM TI (JVM Tool Interface)** cung cấp giao diện native cho agent/debugger tương tác với VM.

Khi bạn bấm Debug trong IDE, IDE thường khởi chạy ứng dụng bằng cấu hình debug hoặc kết nối vào JVM đã bật debug agent. Debugger gửi yêu cầu đặt breakpoint. Khi JVM tới vị trí đó, sự kiện breakpoint được gửi về debugger và thread liên quan bị tạm dừng theo suspend policy.

Bạn có thể xem biến và call stack trong lúc thread đang dừng. Khi bấm Resume/Continue, debugger yêu cầu JVM tiếp tục chạy.

## 3. Chuẩn bị source code và debug information

Debugger cần thông tin ánh xạ từ bytecode trở lại source code.

Khi biên dịch Java bằng javac, mặc định compiler tạo thông tin line number và source file. Muốn có thêm thông tin biến local, dùng `-g`.

~~~bash
javac -g --release 17 LocalDebugDemo.java
~~~

| Tùy chọn | Thông tin được tạo |
|---|---|
| `-g` | Tất cả debug information, gồm source, line number và local variables |
| `-g:lines` | Thông tin line number |
| `-g:source` | Tên source file |
| `-g:vars` | Thông tin local variables |
| `-g:none` | Không tạo debug information |

Nếu không có local-variable information, debugger có thể vẫn dừng tại breakpoint nhưng không hiển thị tên/giá trị biến local. Khi đó hãy biên dịch lại bằng `-g`.

### Source và bytecode phải khớp nhau

Debugger dựa vào line number table trong file `.class`. Nếu source bạn mở khác với source đã tạo ra bytecode đang chạy, breakpoint có thể đặt sai dòng hoặc IDE báo source không khớp.

Trước khi debug:

1. Build lại đúng module và profile cần kiểm tra.
2. Xác nhận IDE chạy đúng output directory/classpath.
3. Đảm bảo source đang mở là phiên bản tạo ra file `.class`.
4. Xóa build artifact cũ khi nghi ngờ class cũ vẫn được sử dụng.
5. Dùng cùng JDK/toolchain như cấu hình ứng dụng cần tái hiện.

Breakpoint thường chỉ hợp lệ ở dòng có bytecode thực thi. Dòng comment, dấu ngoặc hoặc khai báo không tạo instruction có thể không đặt được breakpoint.

## 4. Quy trình debug local bằng IDE

Các IDE Java phổ biến như IntelliJ IDEA, Eclipse và Visual Studio Code với Java extensions đều có chế độ debug. Tên nút và bố cục có thể khác nhau, nhưng quy trình cơ bản tương tự.

### Bước 1: mở đúng project và cấu hình chạy

Kiểm tra:

- Project đã import/build thành công.
- Đúng JDK và language level.
- Đúng main class hoặc test cần chạy.
- Classpath/module path chứa dependency.
- Working directory chính xác.
- Program arguments, environment variables và VM options phù hợp.
- Profile/configuration local có dữ liệu cần tái hiện.

Một chương trình có thể chạy đúng ở terminal nhưng sai trong IDE vì working directory, environment variable hoặc VM option khác nhau.

### Bước 2: đặt breakpoint

Nhấp vào lề bên trái dòng code để tạo breakpoint. Khi chạy bằng Debug, chương trình dừng tại dòng đó trước khi thực thi instruction tương ứng.

Nên đặt breakpoint ở:

- Dòng ngay trước phép tính hoặc điều kiện đáng nghi.
- Đầu method cần kiểm tra.
- Dòng xử lý input từ người dùng hoặc request.
- Nhánh xử lý exception.
- Điểm chuyển trạng thái giữa các bước nghiệp vụ.

Không đặt quá nhiều breakpoint ngay từ đầu. Bắt đầu ở ranh giới giữa input và logic cần điều tra, sau đó thu hẹp vị trí khi đã hiểu luồng thực thi.

### Bước 3: khởi chạy bằng Debug

Chọn cấu hình chạy và bấm Debug. IDE khởi chạy JVM dưới debugger hoặc attach vào JVM đã bật JDWP.

Khi breakpoint được chạm tới, ứng dụng tạm dừng. Debugger thường hiển thị dòng source hiện tại, call stack, biến local và field, thread đang dừng, danh sách breakpoint, watches và expression evaluator.

### Bước 4: kiểm tra trạng thái

Quan sát input trước, rồi kiểm tra từng biến trung gian:

- Giá trị đầu vào có đúng không?
- Kiểu dữ liệu có gây mất độ chính xác không?
- Collection có phần tử như dự kiến không?
- Object có null không?
- Điều kiện if có cho kết quả mong muốn không?
- Biến có bị ghi đè ở một method khác không?
- Call stack có đi qua method mà bạn mong đợi không?

Đừng chỉ nhìn giá trị cuối cùng. Hãy kiểm tra tại thời điểm biến được gán hoặc ngay trước nhánh quyết định.

### Bước 5: chạy từng bước

| Thao tác | Ý nghĩa |
|---|---|
| Resume/Continue | Tiếp tục tới breakpoint hoặc kết thúc chương trình |
| Step Over | Thực thi dòng hiện tại và dừng ở dòng tiếp theo trong frame hiện tại |
| Step Into | Đi vào method được gọi tại dòng hiện tại |
| Step Out | Chạy đến khi method hiện tại trả về caller |
| Run to Cursor | Chạy tới dòng đang chọn nếu IDE hỗ trợ |
| Evaluate Expression | Tính giá trị expression trong context hiện tại |
| Drop Frame | Một số IDE cho phép quay lại caller frame; có thể gây side effect khi chạy lại |

Step Over phù hợp khi bạn tin tưởng method được gọi và chỉ muốn quan sát dòng tiếp theo. Step Into hữu ích khi cần kiểm tra bên trong method. Step Out giúp thoát nhanh khỏi method hiện tại sau khi đã xem đủ thông tin.

### Bước 6: sửa và xác minh

1. Ghi lại input gây lỗi và kết quả sai.
2. Xác định điều kiện hoặc phép tính tạo ra lỗi.
3. Sửa source.
4. Chạy lại test hoặc cấu hình debug với cùng input.
5. Xác nhận kết quả mới đúng.
6. Thử thêm boundary và trường hợp lân cận để tránh tạo regression.

Một lần chạy đúng không đủ chứng minh mọi trường hợp đã được xử lý. Hãy bổ sung test cho tình huống gây lỗi và các giá trị biên.

## 5. Breakpoint và các loại breakpoint

Breakpoint là điểm debugger yêu cầu JVM tạm dừng khi chương trình tới một vị trí hoặc sự kiện xác định.

### Line breakpoint

Dừng tại một dòng source có instruction thực thi. Đây là loại breakpoint phổ biến nhất. Dùng khi đã biết khu vực nghi ngờ và muốn kiểm tra biến trước/sau một phép tính.

### Method breakpoint

Dừng khi method được gọi hoặc bắt đầu thực thi. Hữu ích khi chưa biết caller nào gọi tới method hoặc cần theo dõi một API cụ thể.

Method breakpoint có thể tạo nhiều lần dừng và overhead cao hơn line breakpoint trong method được gọi thường xuyên.

### Exception breakpoint

Dừng khi một exception được throw hoặc khi exception không được catch, tùy loại breakpoint và IDE.

Dùng để tìm nơi exception phát sinh, kể cả khi stack trace cuối cùng chỉ cho thấy nơi exception thoát khỏi ứng dụng.

### Conditional breakpoint

IDE có thể cho phép đặt điều kiện, ví dụ chỉ dừng khi `itemCount == 10`. Cách này hữu ích khi breakpoint nằm trong vòng lặp hoặc method được gọi nhiều lần.

Điều kiện phải là expression hợp lệ trong context hiện tại. Expression có thể được đánh giá nhiều lần và có thể gọi method, vì vậy tránh điều kiện gây side effect hoặc tốn thời gian.

### Logpoint hoặc tracepoint

Một số IDE hỗ trợ ghi message khi tới dòng mà không dừng thread. Dùng để theo dõi giá trị trong luồng chạy liên tục, đặc biệt khi dừng chương trình làm thay đổi timing.

### Field watchpoint

Một số debugger hỗ trợ dừng khi field được đọc hoặc ghi. Tính năng phụ thuộc IDE, VM và loại field. Dùng khi chưa biết nơi nào thay đổi state của object.

## 6. Kiểm tra biến, object và call stack

### Biến local

Biến local chỉ tồn tại trong phạm vi method/frame và thời gian thực thi tương ứng. Để debugger hiển thị tên biến local, class cần được biên dịch với local-variable debug information, thường bằng `javac -g`.

Một local variable có thể chưa được khởi tạo tại dòng hiện tại hoặc đã hết lifetime. Nếu debugger không hiển thị giá trị, hãy kiểm tra vị trí breakpoint và debug information.

### Field và object

Object trong debugger thường có thể mở rộng để xem field. Khi kiểm tra object, chú ý field có null không, collection có size đúng không, object có bị chia sẻ giữa nhiều thread không và field mutable có thay đổi sau khi method khác chạy không.

Evaluate expression hoặc gọi method trong debugger có thể thực thi code của ứng dụng. Nếu method thay đổi state, gửi network request, ghi file hoặc lấy lock, thao tác inspect có thể làm thay đổi chính vấn đề đang điều tra.

### Call stack

Call stack cho biết các method đã gọi tới vị trí hiện tại. Đọc từ frame hiện tại lên các caller để tìm request/event bắt đầu từ đâu, dữ liệu được truyền qua những method nào, method nào đã thay đổi state, có recursion/callback không mong đợi không và exception bắt nguồn từ method nào.

Trong IDE, chọn frame khác trong Call Stack để xem local variables của frame đó. Khi chuyển frame, cần phân biệt biến thuộc caller với biến của method hiện tại.

### Watches

Watch expression giúp theo dõi một biểu thức trong lúc debugger dừng. Ví dụ:

~~~java
itemCount
itemCount >= 10
order.getItems().size()
~~~

Chỉ thêm expression an toàn. Một method call trong watch có thể chạy code thật, gây side effect hoặc làm thay đổi timing.

## 7. Debug exception

Khi exception xảy ra, hãy tìm nơi exception được tạo ra trước khi chỉ sửa dòng cuối cùng trong stack trace.

Quy trình:

1. Bật exception breakpoint cho loại exception cần điều tra.
2. Chọn dừng khi exception được throw hoặc khi exception uncaught, tùy mục tiêu.
3. Khi debugger dừng, xem exception type và message.
4. Đọc call stack và chọn frame đầu tiên thuộc code ứng dụng.
5. Kiểm tra input, object reference và state tại frame đó.
6. Step qua các dòng trước khi exception phát sinh.
7. Xác định điều kiện khiến exception xảy ra và sửa tại nguồn.

Ví dụ với NullPointerException:

- Xác định expression nào chứa reference null.
- Kiểm tra nơi reference được khởi tạo.
- Kiểm tra đường đi của dữ liệu và nhánh có thể bỏ qua assignment.
- Kiểm tra contract của method trả về object đó.
- Thêm validation hoặc xử lý null phù hợp tại ranh giới dữ liệu.

Không chỉ thêm try/catch để che exception nếu nguyên nhân là invariant của ứng dụng bị vi phạm.

## 8. Debug thread và ứng dụng đa luồng

Trong ứng dụng đa luồng, debugger có thể tạm dừng một thread hoặc nhiều thread tùy suspend policy của IDE và sự kiện breakpoint.

Khi dừng ở breakpoint, kiểm tra thread nào đang dừng, thread nào vẫn chạy, thread đang giữ monitor/lock nào, có thread khác đang chờ lock không, có shared mutable state không và một biến có thể bị thread khác thay đổi giữa hai lần quan sát không.

Tạm dừng một thread đang giữ lock có thể khiến thread khác bị block. Nếu suspend tất cả thread, toàn bộ ứng dụng có thể ngừng xử lý trong lúc bạn kiểm tra.

### Race condition

Race condition có thể biến mất khi debugger làm thay đổi timing. Breakpoint dừng thread và làm thay đổi thứ tự tương đối giữa các thao tác.

Để điều tra race condition:

1. Tái hiện bằng test đồng thời có kiểm soát.
2. Ghi log có timestamp và thread name.
3. Dùng thread dump/JFR để quan sát hoạt động theo thời gian.
4. Kiểm tra synchronization, lock ordering, atomic operation và visibility.
5. Dùng breakpoint có chọn lọc, tránh dừng quá lâu trong critical section.
6. Viết test lặp lại nhiều lần để xác nhận bản sửa.

Không xem việc lỗi biến mất khi bật debugger là bằng chứng lỗi đã được sửa.

## 9. Debug virtual thread

Virtual thread có thể được tạo với số lượng lớn. Vì vậy, JDB mặc định không theo dõi tất cả virtual thread ngay khi chúng được tạo; nó theo dõi các virtual thread đã phát sinh event mà debugger quan tâm, chẳng hạn breakpoint.

JDK 26 hỗ trợ tùy chọn:

~~~bash
jdb -trackallthreads LocalDebugDemo
~~~

Tùy chọn này yêu cầu JDB theo dõi virtual thread khi chúng được tạo. Debug Agent cũng có option `includevirtualthreads` để đưa các virtual thread đã biết vào danh sách thread khi kết nối.

Theo dõi tất cả virtual thread có thể tạo lượng thông tin lớn. Debug Agent có thể không biết các virtual thread được tạo trước khi debugger attach. Không dùng danh sách thread hiển thị trong debugger như bằng chứng rằng mọi virtual thread trong process đều đã được liệt kê.

## 10. Dùng jdb để debug local từ terminal

`jdb` là Java Debugger đi kèm JDK. Đây là debugger dòng lệnh minh họa Java Platform Debugger Architecture và có thể launch hoặc kết nối vào JVM local/remote.

Kiểm tra công cụ:

~~~bash
jdb -help
jdb -listconnectors
~~~

### Launch ứng dụng dưới jdb

Nếu main class là `LocalDebugDemo`, chạy:

~~~bash
jdb LocalDebugDemo
~~~

JDB khởi chạy một JVM mới, load class và dừng trước instruction đầu tiên của class ứng dụng. Bạn có thể đặt breakpoint rồi dùng `run` để bắt đầu.

Nếu class nằm trong output directory khác:

~~~bash
jdb -classpath out com.example.LocalDebugDemo
~~~

Có thể dùng `-sourcepath` để chỉ định thư mục chứa source file:

~~~bash
jdb -sourcepath src -classpath out com.example.LocalDebugDemo
~~~

Trên Windows, danh sách nhiều thư mục trong path dùng dấu chấm phẩy; trên Linux/macOS thường dùng dấu hai chấm.

### Các lệnh jdb thường dùng

| Lệnh | Tác dụng |
|---|---|
| `help` hoặc `?` | Hiển thị danh sách lệnh |
| `stop at Class:line` | Đặt breakpoint tại dòng |
| `stop in Class.method` | Đặt breakpoint ở đầu method |
| `clear Class:line` | Xóa breakpoint |
| `run` | Chạy ứng dụng được jdb launch |
| `cont` | Tiếp tục sau breakpoint/step/exception |
| `step` | Đi vào method được gọi ở dòng hiện tại |
| `next` | Chạy qua dòng hiện tại mà không step vào method |
| `step up` | Đi lên caller frame sau khi step |
| `where` | In call stack của thread hiện tại |
| `where all` | In stack của các thread trong thread group hiện tại |
| `threads` | Liệt kê thread debugger đang theo dõi |
| `thread <id>` | Chọn thread hiện tại |
| `locals` | In local variables trong frame hiện tại nếu có debug info |
| `print expression` | In giá trị expression |
| `dump expression` | In field của object |
| `up` / `down` | Chuyển stack frame |
| `catch ExceptionClass` | Dừng khi exception thuộc class được chỉ định bị throw |
| `ignore ExceptionClass` | Bỏ breakpoint exception đã đặt bằng catch |
| `exit` | Thoát debugger |

Tên lệnh và chi tiết hỗ trợ có thể khác giữa JDK release. Dùng `help` trong chính phiên jdb để xác nhận lệnh có sẵn.

### Breakpoint theo dòng và method

Ví dụ:

~~~text
stop at LocalDebugDemo:12
stop in LocalDebugDemo.shippingFee
~~~

Khi method bị overload, chỉ rõ kiểu tham số để chọn đúng method:

~~~text
stop in LocalDebugDemo.calculate(int,java.lang.String)
~~~

`stop` không có đối số sẽ liệt kê breakpoint hiện tại. `clear` không có đối số cũng có thể dùng để xem các breakpoint.

### Đọc source và biến

Khi dừng tại breakpoint:

~~~text
list
locals
print itemCount
where
~~~

`list` hiển thị source quanh vị trí hiện tại nếu debugger tìm thấy source. `locals` và `print` giúp xem biến trong stack frame đang chọn. Nếu không xem được biến local, kiểm tra class có được compile với `-g` hay không.

## 11. Ví dụ thực hành: tìm lỗi điều kiện bằng jdb

Ví dụ này có một lỗi boundary: nghiệp vụ yêu cầu đơn hàng từ 10 sản phẩm trở lên được miễn phí giao hàng, nhưng code lại dùng `>` thay vì `>=`.

Tạo file `LocalDebugDemo.java`:

~~~java
public class LocalDebugDemo {
    private static int shippingFee(int itemCount) {
        if (itemCount > 10) {
            return 0;
        }
        return 25;
    }

    public static void main(String[] args) {
        int itemCount = 10;
        int fee = shippingFee(itemCount);

        System.out.println("items=" + itemCount);
        System.out.println("shippingFee=" + fee);
    }
}
~~~

### Bước 1: biên dịch có debug information

~~~bash
javac -g --release 17 LocalDebugDemo.java
~~~

### Bước 2: chạy bình thường để tái hiện

~~~bash
java LocalDebugDemo
~~~

Output chính xác trước khi sửa:

~~~text
items=10
shippingFee=25
~~~

Theo yêu cầu nghiệp vụ, kết quả này sai vì 10 sản phẩm phải được miễn phí giao hàng.

### Bước 3: launch bằng jdb

~~~bash
jdb -classpath . LocalDebugDemo
~~~

Tại dấu nhắc của jdb, đặt breakpoint đầu method:

~~~text
stop in LocalDebugDemo.shippingFee
run
~~~

JDB sẽ dừng khi method `shippingFee` được gọi.

### Bước 4: kiểm tra input và call stack

~~~text
where
locals
print itemCount
list
~~~

Xác nhận `itemCount` có giá trị 10, call stack cho thấy `main` gọi `shippingFee` và source đang hiển thị đúng phiên bản code cần kiểm tra.

### Bước 5: đi qua điều kiện

Dùng `next` để thực thi từng dòng mà không đi vào method khác:

~~~text
next
list
~~~

Quan sát điều kiện `itemCount > 10`. Với input 10, biểu thức này là false, nên chương trình đi tới `return 25`.

Có thể kiểm tra biểu thức:

~~~text
print itemCount > 10
~~~

Giá trị logic cần thấy là false. Đây là nguyên nhân trực tiếp khiến nhánh miễn phí không được chọn.

### Bước 6: tiếp tục để xem output

~~~text
cont
~~~

Ứng dụng hoàn tất và in:

~~~text
items=10
shippingFee=25
~~~

### Bước 7: sửa lỗi

Sửa điều kiện trong `shippingFee` thành:

~~~java
if (itemCount >= 10) {
    return 0;
}
~~~

Biên dịch lại và chạy:

~~~bash
javac -g --release 17 LocalDebugDemo.java
java LocalDebugDemo
~~~

Output chính xác sau khi sửa:

~~~text
items=10
shippingFee=0
~~~

### Bước 8: kiểm tra boundary lân cận

Ngoài 10, cần kiểm tra ít nhất các giá trị:

| itemCount | Kết quả mong đợi |
|---:|---:|
| 0 | 25 |
| 9 | 25 |
| 10 | 0 |
| 11 | 0 |

Nếu nghiệp vụ không cho phép itemCount âm, hãy xác nhận validation ở nơi nhận dữ liệu. Ví dụ này minh họa cách debugger giúp tìm điều kiện sai; nó không thay thế test cho các trường hợp biên.

## 12. Attach jdb vào JVM local đang chạy

Launch bằng jdb là cách đơn giản khi có thể chủ động khởi chạy ứng dụng. Nếu ứng dụng đã chạy và được cấu hình debug agent từ đầu, có thể attach debugger vào process đó.

### Bước 1: khởi chạy JVM với JDWP

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 LocalDebugDemo
~~~

Ý nghĩa:

- `transport=dt_socket`: dùng socket transport.
- `server=y`: JVM đích lắng nghe kết nối debugger.
- `suspend=n`: JVM không chờ debugger attach mới chạy main.
- `address=127.0.0.1:5005`: lắng nghe trên loopback local, cổng 5005.

Nếu cần debugger attach trước khi main chạy, dùng `suspend=y`. JVM sẽ tạm dừng lúc khởi tạo debug session cho đến khi debugger kết nối và tiếp tục.

### Bước 2: attach bằng jdb

Mở terminal khác trên cùng máy:

~~~bash
jdb -attach 127.0.0.1:5005
~~~

Đặt breakpoint:

~~~text
stop in LocalDebugDemo.shippingFee
~~~

Vì JVM có thể đã chạy qua method trước khi attach, cần kích hoạt lại luồng xử lý hoặc dùng một request/test tiếp theo để chạm breakpoint.

### Bước 3: xác minh và thoát

Dùng `where`, `locals`, `print`, `threads` và `cont` như phiên launch. Khi kết thúc, dùng `exit` để đóng debugger. Ứng dụng đích có thể tiếp tục chạy tùy trạng thái và cách debugger detach.

Không thể mặc định attach debugger vào một JVM bất kỳ nếu JVM không được khởi chạy với debug agent/connector phù hợp. Nếu cần debug local process, hãy cấu hình debug lúc khởi chạy hoặc dùng IDE để launch bằng Debug.

## 13. Debug local bằng IDE so với jdb

| Tiêu chí | IDE debugger | jdb |
|---|---|---|
| Cách thao tác | Giao diện đồ họa | Terminal |
| Breakpoint | Line, method, conditional, exception tùy IDE | Line, method, exception và các lệnh được hỗ trợ |
| Xem biến | Cửa sổ Variables/Watches | `locals`, `print`, `dump` |
| Call stack | Cửa sổ Call Stack | `where`, `up`, `down` |
| Step | Nút Step Into/Over/Out | `step`, `next`, `step up` |
| Phù hợp | Phát triển hằng ngày, project lớn | Môi trường terminal, kiểm tra nhanh, học JPDA |
| Source mapping | IDE quản lý project/source | Cần classpath và sourcepath phù hợp |

IDE thường thuận tiện hơn khi cần duyệt object graph, xem nhiều frame và đặt conditional breakpoint. jdb hữu ích khi môi trường chỉ có terminal hoặc muốn hiểu debugger hoạt động qua các lệnh cơ bản.

## 14. Cấu hình local cần kiểm tra khi chương trình không chạy đúng

Khi debug local, một cấu hình chạy khác cấu hình terminal có thể tạo ra hành vi khác nhau.

Kiểm tra JDK runtime thực tế, classpath/module path, working directory, program arguments, environment variables, system properties truyền bằng `-D`, VM options, file cấu hình local/profile, port và dependency service, test data và trạng thái database/cache.

Nếu chương trình chạy với profile `dev` nhưng lỗi xảy ra ở profile `test`, debug local cần dùng đúng profile để tái hiện. Không sửa code dựa trên kết quả của một cấu hình không tương ứng với môi trường gây lỗi.

### Kiểm tra JDK và class được chạy

~~~bash
java -version
javac -version
jdb -help
~~~

Nếu có nhiều JDK cài trên máy, xác nhận `java`, `javac` và `jdb` cùng thuộc toolchain mong muốn. Trên Windows có thể dùng `where java`, `where javac`, `where jdb`; trên Linux/macOS có thể dùng `which java`, `which javac`, `which jdb`.

## 15. Debug local và test tự động

Debugger giúp quan sát trạng thái một lần chạy. Test tự động giúp xác nhận hành vi lặp lại được.

Một quy trình tốt:

1. Viết test tái hiện lỗi với input nhỏ nhất.
2. Chạy test và xác nhận nó thất bại theo cách dự kiến.
3. Đặt breakpoint tại method xử lý logic.
4. Debug để kiểm tra input, branch và state.
5. Sửa code.
6. Chạy lại test để xác nhận pass.
7. Chạy thêm test boundary và regression.
8. Gỡ breakpoint hoặc tắt debug configuration trước khi chạy test suite thông thường.

Với bug trong ví dụ shipping fee, có thể tạo test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ShippingFeeTest {
    @Test
    void tenItemsAreEligibleForFreeShipping() {
        assertEquals(0, LocalDebugDemo.shippingFee(10));
    }
}
~~~

Đoạn test chỉ minh họa assertion và giả định method được đổi thành package-visible để test gọi được. Nếu giữ method `private`, hãy kiểm thử qua public API hoặc thiết kế lại ranh giới kiểm thử phù hợp.

Không dùng debugger làm bằng chứng duy nhất rằng bug đã được sửa. Hãy giữ test tái hiện lỗi trong bộ regression.

## 16. Các giới hạn và tác động của debug

Debugging thay đổi cách ứng dụng được điều khiển:

- Breakpoint làm thread dừng và có thể làm thay đổi timing.
- Suspend all có thể dừng cả các thread khác.
- Method evaluation có thể thực thi code và gây side effect.
- Conditional breakpoint có thể được đánh giá thường xuyên.
- Debug agent có thể làm tăng overhead.
- Debugger có thể không hiển thị đầy đủ local variable nếu class thiếu debug information.
- Source khác bytecode có thể khiến breakpoint lệch dòng.
- JIT optimization và compiler có thể khiến một số biến hoặc dòng source khó quan sát như kỳ vọng.

Vì vậy, debugger rất hữu ích để hiểu một lần thực thi, nhưng không phải lúc nào cũng phù hợp để đo hiệu năng hoặc điều tra lỗi nhạy với timing. Dùng JFR, profiler, GC log và application metrics khi cần quan sát hành vi trong thời gian dài.

## 17. An toàn khi bật JDWP

JDWP cho debugger quyền điều khiển và kiểm tra JVM đích. Nếu socket debug mở trên network interface không tin cậy, người có thể kết nối vào có thể kiểm soát quá trình thực thi và truy cập dữ liệu trong process.

Khi debug local:

- Ưu tiên loopback như `127.0.0.1`.
- Không bind wildcard `*` nếu không có nhu cầu và biện pháp kiểm soát rõ ràng.
- Không mở debug port ra Internet.
- Dùng firewall và giới hạn nguồn kết nối nếu phải debug qua network.
- Tắt debug agent sau khi hoàn thành.
- Không bật JDWP trong production như cấu hình mặc định.
- Bảo vệ terminal output và dữ liệu đang hiển thị trong debugger.

Ví dụ `address=127.0.0.1:5005` ở trên giới hạn socket vào loopback. Nếu đổi thành `*:5005`, JVM lắng nghe trên mọi network interface; chỉ làm điều đó khi đã có kiểm soát truy cập phù hợp.

## 18. Lỗi thường gặp và cách xử lý

### Breakpoint không được kích hoạt

**Dấu hiệu:** ứng dụng chạy qua dòng nhưng debugger không dừng.

**Nguyên nhân:** class chưa được load, breakpoint ở dòng không có bytecode, code đang chạy từ class cũ hoặc breakpoint chưa được bind.

**Cách xử lý:** xác nhận đúng process và classpath; build lại; kiểm tra breakpoint đặt trên dòng thực thi; dùng method breakpoint để xác định method có được gọi không.

### Breakpoint hiển thị nhưng source không khớp

**Dấu hiệu:** debugger dừng ở dòng khác hoặc báo source mismatch.

**Nguyên nhân:** source hiện tại khác bytecode đã compile, output directory chứa class cũ hoặc IDE chạy nhầm module.

**Cách xử lý:** clean/rebuild đúng module; xác nhận run configuration; kiểm tra classpath và sourcepath; mở đúng source revision.

### Không xem được local variables

**Dấu hiệu:** debugger báo local variable information unavailable hoặc không hiển thị tên biến.

**Nguyên nhân:** class được compile thiếu local-variable debug information.

**Cách xử lý:** biên dịch bằng `javac -g`; nếu dùng build tool, bật debug information theo cấu hình compiler của tool; build lại và chạy đúng class mới.

### jdb không tìm thấy main class

**Dấu hiệu:** JDB báo class không tồn tại hoặc không load được.

**Nguyên nhân:** sai classpath, tên class thiếu package hoặc chạy từ sai working directory.

**Cách xử lý:** dùng `jdb -classpath out package.MainClass`; kiểm tra package declaration và vị trí `.class`; bảo đảm dependency có trong classpath/module path.

### jdb attach thất bại

**Dấu hiệu:** lỗi connection refused, timeout hoặc không attach được.

**Nguyên nhân:** JVM chưa bật JDWP, sai host/port, process đã dừng, firewall chặn hoặc debug agent đang ở chế độ client thay vì server.

**Cách xử lý:** kiểm tra `-agentlib:jdwp`, `server=y`, địa chỉ/port và trạng thái JVM; xác nhận debugger và JVM dùng cùng transport; thử kết nối loopback khi debug local.

### JVM bị treo trước main

**Dấu hiệu:** ứng dụng không chạy sau khi khởi động với debug agent.

**Nguyên nhân:** `suspend=y` khiến JVM chờ debugger kết nối trước khi thực thi main.

**Cách xử lý:** attach debugger rồi dùng Resume/Continue; nếu không cần dừng trước main, dùng `suspend=n`.

### Không thấy thread cần tìm

**Dấu hiệu:** danh sách thread trong debugger không có thread mong muốn.

**Nguyên nhân:** thread chưa được tạo, đã kết thúc, debugger không theo dõi toàn bộ virtual thread hoặc thread thuộc process khác.

**Cách xử lý:** xác nhận đúng JVM; dùng `threads`/thread view; trên JDK hỗ trợ, cân nhắc `jdb -trackallthreads`; kết hợp thread dump/JFR để xem hoạt động rộng hơn.

### Debugger làm lỗi timing biến mất

**Dấu hiệu:** race condition không còn xuất hiện khi đặt breakpoint.

**Nguyên nhân:** tạm dừng thread đã thay đổi lịch thực thi và quan hệ thời gian.

**Cách xử lý:** dùng logging có timestamp, stress test, JFR và kiểm tra synchronization; hạn chế breakpoint trong critical section.

### Evaluate expression làm thay đổi state

**Dấu hiệu:** sau khi inspect object, ứng dụng có hành vi khác.

**Nguyên nhân:** expression gọi method có side effect, lấy lock hoặc thực hiện I/O.

**Cách xử lý:** chỉ inspect field/giá trị đơn giản khi có thể; tránh gọi method mutating; dùng watch expression an toàn và kiểm tra code của method trước khi evaluate.

### Chương trình chạy trong IDE khác terminal

**Dấu hiệu:** cùng source nhưng output hoặc lỗi khác nhau.

**Nguyên nhân:** JDK, profile, environment variable, working directory, VM option hoặc program argument khác.

**Cách xử lý:** so sánh toàn bộ run configuration với lệnh terminal; xác nhận đúng file cấu hình và dependency service.

## 19. Checklist debug local

### Trước khi debug

- [ ] Tái hiện được lỗi bằng input hoặc test xác định.
- [ ] Chọn đúng JDK và run configuration.
- [ ] Build đúng module và source revision.
- [ ] Bảo đảm source khớp bytecode.
- [ ] Tạo debug information bằng `-g` nếu cần xem local variables.
- [ ] Kiểm tra working directory, arguments, environment và VM options.
- [ ] Đặt breakpoint ở vị trí có ý nghĩa.

### Trong khi debug

- [ ] Xác nhận breakpoint được kích hoạt.
- [ ] Kiểm tra input trước khi xem kết quả.
- [ ] Đọc call stack để xác định caller.
- [ ] Dùng Step Over/Into/Out đúng mục đích.
- [ ] Quan sát biến trước và sau nhánh quyết định.
- [ ] Kiểm tra exception tại nơi được throw.
- [ ] Chú ý thread và suspend policy.
- [ ] Tránh evaluate method có side effect.

### Sau khi debug

- [ ] Ghi lại nguyên nhân và input tái hiện.
- [ ] Sửa code tại nguồn.
- [ ] Thêm test tái hiện bug.
- [ ] Kiểm tra boundary và regression.
- [ ] Chạy lại test/build.
- [ ] Xóa breakpoint tạm và dừng debug agent.
- [ ] Không để debug port mở sau khi hoàn thành.

## 20. Tài liệu tham khảo chính thức

- [The jdb Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdb.html) — launch/attach JVM, breakpoint, stepping, exception, sourcepath, connectors và virtual-thread tracking.
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — tùy chọn -g, -g:lines, -g:vars, -g:source và -g:none.
- [Java Platform Debugger Architecture: Connection and Invocation — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html) — JDWP agent, socket/shared-memory transport, server/client, suspend và connector.
- [Java Debug Wire Protocol — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jdwp/jdwp-protocol.html) — giao thức giữa debugger và target JVM.
- [Java Debug Interface — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jdi/module-summary.html) — API JDI dành cho debugger và công cụ quản trị.
- [Troubleshooting Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf) — hướng dẫn dùng jdb và JDWP để debug ứng dụng.

Debug local giúp bạn quan sát chính xác input, branch, biến và call stack tại thời điểm lỗi xảy ra. Hãy tái hiện lỗi bằng một test nhỏ, đặt breakpoint có mục tiêu, kiểm tra source/bytecode và debug information, sau đó xác nhận bản sửa bằng test tự động để kết quả có thể lặp lại.
