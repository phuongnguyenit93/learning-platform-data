# Kiểu trả về cụ thể hơn trong chuỗi lời gọi ByteBuffer

## Mục tiêu

Từ Java 9, các phương thức thay đổi trạng thái được kế thừa từ `Buffer` trong `ByteBuffer` có kiểu trả về cụ thể hơn: `ByteBuffer` thay vì `Buffer`.

Thay đổi này dùng cơ chế **covariant return type** (kiểu trả về hiệp biến). Nó giúp giữ nguyên kiểu tĩnh của đối tượng trong chuỗi lời gọi, nhờ đó có thể gọi tiếp các phương thức riêng của `ByteBuffer` mà không cần ép kiểu.

Điểm thay đổi nằm ở kiểu trả về trong API. Các phương thức vẫn thao tác trên cùng một buffer và tuân theo quy tắc position, limit, mark như trước.

## 1. Buffer và ByteBuffer

`Buffer` là lớp cơ sở trừu tượng đại diện cho vùng dữ liệu có trạng thái. `ByteBuffer` kế thừa `Buffer` để đọc và ghi dữ liệu byte.

Một buffer có các trạng thái chính:

- **capacity:** tổng số phần tử mà buffer có thể chứa.
- **limit:** giới hạn đọc hoặc ghi hiện tại; thao tác không được vượt quá limit.
- **position:** vị trí của phần tử tiếp theo sẽ được đọc hoặc ghi.
- **mark:** vị trí đã đánh dấu để có thể quay lại bằng `reset()`.

Các phương thức như `position(int)`, `limit(int)`, `mark()`, `reset()`, `clear()`, `flip()` và `rewind()` được khai báo ở lớp `Buffer`. Trong Java 8, kiểu trả về của các phương thức này là `Buffer`.

Vì `ByteBuffer` là lớp con, Java 9 bổ sung các override có kiểu trả về `ByteBuffer`. Nhờ đó, kết quả của một lời gọi vẫn có thể được dùng như một ByteBuffer ngay trong biểu thức tiếp theo.

## 2. Covariant return type là gì?

Covariant return type cho phép một phương thức override trả về kiểu con cụ thể hơn kiểu trả về được khai báo trong phương thức của lớp cha.

Ví dụ đơn giản:

~~~java
class Parent {
    Parent reset() {
        return this;
    }
}

class Child extends Parent {
    @Override
    Child reset() {
        return this;
    }
}
~~~

Phương thức `Child.reset()` override `Parent.reset()`, nhưng trả về `Child`, là kiểu con của `Parent`. Đây là kiểu override hợp lệ trong Java.

Áp dụng vào ByteBuffer:

- Phương thức trong lớp cơ sở Buffer trả về Buffer.
- ByteBuffer override phương thức đó và trả về ByteBuffer.
- Mã gọi phương thức trên một biểu thức có kiểu ByteBuffer nhận lại kiểu ByteBuffer ở mức biên dịch.

Thay đổi này không tạo ra một buffer mới. Những phương thức như `position(int)`, `limit(int)` và `flip()` vẫn thay đổi trạng thái của chính đối tượng đang được gọi và trả lại tham chiếu đến đối tượng đó.

## 3. Những phương thức ByteBuffer có kiểu trả về cụ thể từ Java 9

Các override quan trọng gồm:

| Phương thức | Tác dụng | Kiểu trả về trong ByteBuffer từ Java 9 |
|---|---|---|
| `position(int newPosition)` | Đặt vị trí đọc/ghi tiếp theo | `ByteBuffer` |
| `limit(int newLimit)` | Đặt giới hạn đọc/ghi | `ByteBuffer` |
| `mark()` | Lưu vị trí hiện tại | `ByteBuffer` |
| `reset()` | Quay lại vị trí đã mark | `ByteBuffer` |
| `clear()` | Chuẩn bị buffer cho lần ghi mới | `ByteBuffer` |
| `flip()` | Chuyển từ chế độ ghi sang đọc dữ liệu vừa ghi | `ByteBuffer` |
| `rewind()` | Đưa position về 0 để đọc lại | `ByteBuffer` |

Các phương thức này đã tồn tại từ trước; thay đổi ở Java 9 là kiểu trả về cụ thể hơn trong lớp ByteBuffer. Các phương thức ghi/đọc như `put(byte)`, `putInt(int)`, `get()` vẫn có hợp đồng riêng: phương thức ghi trả về ByteBuffer để chaining, còn `get()` trả về một byte.

## 4. Trước Java 9: chuỗi gọi bị mất kiểu ByteBuffer

Trong Java 8, lời gọi `flip()` được nhìn nhận theo kiểu trả về `Buffer`. Vì vậy, đoạn mã sau không biên dịch với source level Java 8:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8)
        .putInt(0x01020304)
        .flip();
~~~

Trình biên dịch báo lỗi vì kết quả cuối cùng có kiểu tĩnh `Buffer`, không thể gán trực tiếp cho biến `ByteBuffer`.

Một cách viết tương thích với Java 8 là tách thao tác thành các câu lệnh:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.putInt(0x01020304);
buffer.flip();
~~~

Cách này vẫn hoạt động vì lời gọi `flip()` được dùng như một câu lệnh và giá trị trả về không cần gán vào biến ByteBuffer.

## 5. Từ Java 9: có thể giữ kiểu ByteBuffer trong chuỗi gọi

Với override covariant return type, có thể viết:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8)
        .putInt(0x01020304)
        .flip()
        .position(1)
        .limit(3);
~~~

Mỗi phương thức thay đổi trạng thái trả về ByteBuffer nên lời gọi tiếp theo vẫn thấy các phương thức của ByteBuffer.

Có thể tiếp tục gọi `mark()`, `position(int)`, `reset()`, `clear()` hoặc `rewind()` trong cùng chuỗi:

~~~java
buffer.position(1)
        .mark()
        .position(2)
        .reset();
~~~

Sau chuỗi trên, position quay về vị trí đã đánh dấu là 1.

Điều quan trọng là compiler giữ kiểu tĩnh ByteBuffer xuyên suốt biểu thức. Đây là lợi ích chính của thay đổi API trong Java 9.

## 6. Hiểu đúng các thao tác trạng thái khi chaining

Chaining không thay đổi ngữ nghĩa của các phương thức. Cần hiểu trạng thái buffer để tránh gọi chúng sai thứ tự.

### position(int)

Đặt vị trí đọc hoặc ghi tiếp theo. Giá trị mới phải nằm trong khoảng từ 0 đến limit hiện tại. Khi position thay đổi xuống trước mark đã lưu, mark bị loại bỏ.

### limit(int)

Đặt giới hạn mới trong khoảng từ 0 đến capacity. Nếu limit mới nhỏ hơn position hiện tại, position cũng được điều chỉnh xuống bằng limit mới. Mark nằm ngoài limit mới sẽ bị loại bỏ.

### mark() và reset()

`mark()` lưu position hiện tại. `reset()` khôi phục position về mark. Nếu chưa có mark hợp lệ hoặc mark đã bị loại bỏ do thay đổi trạng thái, `reset()` ném `InvalidMarkException`.

### clear()

Đặt position về 0, limit về capacity và xóa mark. Đây là thao tác chuẩn bị cho việc ghi dữ liệu mới. `clear()` không xóa hoặc đặt các byte bên trong về 0; dữ liệu cũ vẫn nằm trong vùng nhớ nhưng không còn được xem là nội dung hiện hành theo trạng thái buffer.

### flip()

Dùng sau khi ghi xong để chuẩn bị đọc: limit được đặt bằng position hiện tại, position trở về 0 và mark bị xóa. Chỉ phần dữ liệu vừa ghi nằm trong vùng có thể đọc.

### rewind()

Đặt position về 0 và xóa mark, nhưng giữ nguyên limit. Dùng khi muốn đọc lại vùng dữ liệu hiện tại.

Vì các phương thức này có tác dụng khác nhau, không nên ghép chúng thành một chuỗi dài nếu người đọc khó theo dõi được trạng thái trước và sau mỗi bước.

## 7. Ví dụ hoàn chỉnh có thể chạy

Tệp `ByteBufferChainDemo.java`:

~~~java
import java.nio.ByteBuffer;

public class ByteBufferChainDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(8)
                .putInt(0x01020304)
                .put((byte) 0x05)
                .flip()
                .position(1)
                .limit(4)
                .mark()
                .position(2)
                .reset();

        System.out.println("position after reset: " + buffer.position());
        System.out.println("limit: " + buffer.limit());
        System.out.println("next byte: " + buffer.get());
        System.out.println("position after get: " + buffer.position());

        buffer.clear().position(2).limit(6).rewind();
        System.out.println("position after rewind: " + buffer.position());
        System.out.println("limit after rewind: " + buffer.limit());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all ByteBufferChainDemo.java
java ByteBufferChainDemo
~~~

Kết quả chuẩn:

~~~text
position after reset: 1
limit: 4
next byte: 2
position after get: 2
position after rewind: 0
limit after rewind: 6
~~~

Giải thích:

1. `putInt(0x01020304)` ghi bốn byte, sau đó `put((byte) 0x05)` ghi thêm một byte.
2. `flip()` đặt limit thành 5 và position về 0 để đọc.
3. `position(1)` và `limit(4)` chọn vùng byte ở các vị trí 1 đến 3.
4. `mark()` lưu position 1; sau khi position chuyển sang 2, `reset()` đưa position về 1.
5. `get()` đọc byte ở vị trí 1, có giá trị 2 theo byte mặc định big-endian của ByteBuffer.
6. `clear()` đặt lại trạng thái ghi; các lời gọi tiếp theo đổi position, limit rồi rewind về đầu vùng đọc hiện tại.

## 8. Kiểm tra khác biệt bằng source level

Có thể dùng cùng một đoạn mã để quan sát sự khác biệt giữa API Java 8 và Java 9.

Với Java 8:

~~~bash
javac --release 8 ByteBufferChainDemo.java
~~~

Đoạn chaining gán kết quả vào ByteBuffer không biên dịch vì một số phương thức được nhìn nhận là trả về Buffer.

Với Java 9 trở lên:

~~~bash
javac --release 9 ByteBufferChainDemo.java
java ByteBufferChainDemo
~~~

Đoạn mã biên dịch vì các override trong ByteBuffer trả về ByteBuffer. Nếu dự án cần tương thích source level Java 8, hãy tách các thao tác trạng thái thành nhiều câu lệnh hoặc dùng cách chuyển kiểu có chủ đích sau khi hiểu rõ kiểu trả về.

## 9. Lỗi thường gặp và lưu ý thiết kế

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gán kết quả `flip()` cho ByteBuffer khi biên dịch source level Java 8 | Kiểu trả về khi đó là Buffer | Tách câu lệnh hoặc nâng source level lên Java 9+ |
| Nghĩ covariant return tạo ra buffer mới | Nhầm kiểu trả về với thao tác tạo view | Nhớ rằng các phương thức trạng thái này thay đổi cùng đối tượng |
| Gọi `reset()` khi chưa mark | Không có mark hợp lệ | Gọi mark trước hoặc xử lý InvalidMarkException |
| Gọi `get()` rồi tiếp tục chain như thể nó trả về ByteBuffer | `get()` trả về byte | Chỉ chain các phương thức trả về ByteBuffer |
| Gọi `clear()` rồi cho rằng dữ liệu đã bị xóa | clear chỉ đặt lại position, limit và mark | Ghi đè dữ liệu nếu cần xóa nội dung; xử lý dữ liệu nhạy cảm theo yêu cầu riêng |
| Chain quá dài, khó thấy chuyển trạng thái đọc/ghi | Nhiều thao tác thay đổi state liên tiếp | Chia thành các câu lệnh có tên và chú thích khi cần |
| Dùng chaining nhưng quên giới hạn hiện tại | position phải nằm trong vùng hợp lệ của limit | Kiểm tra capacity, limit và position trước khi đặt trạng thái |

Chaining phù hợp với các bước cấu hình ngắn và dễ đọc. Với pipeline đọc/ghi phức tạp, nên tách thao tác ghi, flip, đọc và rewind thành từng bước rõ ràng để dễ kiểm thử.

## 10. Checklist ghi nhớ

- Java 9 bổ sung các override covariant trong ByteBuffer cho các phương thức trạng thái kế thừa từ Buffer.
- Các phương thức chính gồm position(int), limit(int), mark(), reset(), clear(), flip() và rewind().
- Kiểu trả về cụ thể hơn là ByteBuffer thay vì Buffer.
- Thay đổi giúp giữ kiểu tĩnh ByteBuffer trong chuỗi lời gọi và bỏ nhu cầu ép kiểu trong các trường hợp chaining.
- Các phương thức vẫn thay đổi trạng thái của cùng buffer.
- clear() không xóa dữ liệu; flip() chuẩn bị đọc dữ liệu vừa ghi; rewind() đọc lại vùng hiện tại.
- reset() cần mark hợp lệ.
- get() trả về byte nên không thể chain tiếp như phương thức trả về ByteBuffer.
- Kiểm tra source level nếu dự án cần tương thích Java 8.
- Ưu tiên chuỗi gọi ngắn, dễ đọc và dễ kiểm tra trạng thái.

Covariant return type trong ByteBuffer làm API fluent hơn từ Java 9: các thao tác trạng thái trả về đúng kiểu ByteBuffer, vì vậy có thể kết hợp chúng trực tiếp mà vẫn giữ được kiểu cụ thể ở thời điểm biên dịch.