# Tác động khi phương thức thay đổi hoặc làm lộ mảng tham số

Varargs giúp lời gọi ngắn gọn, nhưng tham số bên trong phương thức vẫn là mảng. Nếu phương thức sửa mảng, giữ lại mảng hoặc trả mảng ra ngoài, dữ liệu có thể bị thay đổi từ một nơi mà người dùng API không ngờ tới.

Vấn đề cốt lõi là **ai đang cùng giữ tham chiếu đến một mảng, và ai được phép sửa nó**. Dấu `...` không tự tạo quyền sở hữu riêng hay tính bất biến cho dữ liệu.

## 1. Khi nào người gọi và phương thức dùng chung mảng?

Xét khai báo minh họa trong một lớp:

```java
static void overwrite(int... values) {
    values[0] = 99;
}
```

Với `overwrite(1, 2)`, lời gọi chuẩn bị mảng chứa hai giá trị. Mảng đó không phải một mảng có tên đã được người gọi truyền vào.

Với cách gọi sau, người gọi và biến tham số cùng trỏ đến **một đối tượng mảng**:

```java
int[] input = {1, 2};
overwrite(input);
System.out.println(input[0]);  // 99
```

Java truyền tham số theo giá trị. Giá trị được truyền ở đây là tham chiếu đến mảng; không phải bản sao toàn bộ mảng.

Có thể hình dung:

```text
input  ──┐
         ├──> int[] {1, 2}
values ──┘
```

Việc gán `values[0] = 99` sửa đối tượng dùng chung. Khi phương thức kết thúc, thay đổi ấy vẫn tồn tại.

Ngược lại, câu lệnh `values = new int[] {7, 8}` chỉ gán lại biến tham số cục bộ. Nó không khiến biến `input` của người gọi trỏ sang mảng mới.

### final không ngăn sửa phần tử

```java
static void change(final int... values) {
    values[0] = 99;             // Hợp lệ.
    // values = new int[0];     // Không hợp lệ vì biến tham số là final.
}
```

`final` hạn chế việc gán lại biến; nó không biến đối tượng mảng thành bất biến.

Các ví dụ sửa phần tử đầu tiên giả định mảng khác `null` và có ít nhất một phần tử. API thực tế phải quy định, kiểm tra hoặc xử lý trường hợp rỗng/null.

## 2. Hai hướng làm lộ dữ liệu

### Giữ lại mảng đầu vào

Một constructor hoặc phương thức có thể lưu mảng vào trường:

```java
// Đoạn minh họa bên trong một lớp.
private final int[] values;

Buffer(int... values) {
    this.values = values;
}
```

Nếu người gọi truyền một mảng có sẵn, họ vẫn có thể sửa nội dung sau khi constructor hoàn tất. Đối tượng `Buffer` sẽ quan sát sự thay đổi dù không có phương thức cập nhật nào của nó được gọi.

Điều này có thể phá vỡ giả định “dữ liệu đã được kiểm tra khi tạo đối tượng”: ví dụ, giá trị được xác nhận là không âm rồi bị bên ngoài đổi thành số âm.

### Trả ra mảng nội bộ

Nếu getter trả thẳng trường mảng, người nhận có thể sửa dữ liệu nội bộ:

```java
int[] values() {
    return values;
}
```

Đầu vào và đầu ra là hai ranh giới độc lập:

- Chỉ sao chép khi nhận vào vẫn chưa đủ nếu getter trả mảng nội bộ.
- Chỉ sao chép khi trả ra vẫn chưa đủ nếu trường nội bộ dùng chung mảng đầu vào.

Một đường làm lộ khác là đưa mảng vào trường tĩnh, bộ nhớ đệm, callback hoặc công việc chạy sau. Người dùng API có thể không nhìn thấy đường đi đó, nhưng các bên vẫn dùng chung dữ liệu.

## 3. Sao chép phòng vệ đúng ranh giới

Sao chép phòng vệ (defensive copying) tạo mảng riêng tại ranh giới cần bảo vệ.

Với mảng nguyên thủy:

```java
this.values = values.clone();   // Tách mảng được lưu khỏi mảng đầu vào.
return this.values.clone();    // Tách mảng trả ra khỏi mảng nội bộ.
```

Có thể dùng `Arrays.copyOf(values, values.length)` cho mục đích sao chép tương tự. Việc chọn hàm không thay thế quyết định quan trọng hơn: cần tách dữ liệu tại ranh giới nào.

Nếu có kiểm tra nội dung, nên kiểm tra bản sao sẽ được lưu, thay vì kiểm tra mảng đầu vào rồi mới tạo bản sao trong khi bên khác còn có thể sửa nó. Tuy nhiên, sao chép không tự cung cấp một ảnh chụp nguyên tử khi có luồng khác sửa đồng thời; tình huống đó vẫn cần hợp đồng đồng bộ phù hợp.

Không phải phương thức nào cũng phải sao chép. Một hàm tính tổng chỉ đọc mảng trong thời gian gọi có thể không cần bản sao. Một hàm sắp xếp tại chỗ chủ đích sửa dữ liệu có thể dùng trực tiếp, nhưng cần công bố rõ hành vi và dùng tên API dễ hiểu.

## 4. Chương trình kiểm chứng đầy đủ

Lưu thành `VarargsOwnershipDemo.java`. Chương trình chạy trên Java 17+.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class VarargsOwnershipDemo {
    static void overwrite(int... values) {
        values[0] = 99;
    }

    static void rebind(int... values) {
        values = new int[] {7, 8};
    }

    static final class BorrowedBuffer {
        private final int[] values;

        BorrowedBuffer(int... values) {
            this.values = Objects.requireNonNull(values);
        }

        int[] values() {
            return values;
        }
    }

    static final class OwnedBuffer {
        private final int[] values;

        OwnedBuffer(int... values) {
            this.values = Objects.requireNonNull(values).clone();
        }

        int[] snapshot() {
            return values.clone();
        }
    }

    static final class Tag {
        String name;

        Tag(String name) {
            this.name = name;
        }
    }

    static List<String> view(String... names) {
        return Arrays.asList(names);
    }

    static List<String> snapshot(String... names) {
        return List.copyOf(Arrays.asList(names));
    }

    public static void main(String[] args) {
        int[] input = {1, 2};
        overwrite(input);
        System.out.println("after overwrite: " + Arrays.toString(input));
        rebind(input);
        System.out.println("after rebind: " + Arrays.toString(input));

        int[] scores = {10, 20};
        BorrowedBuffer borrowed = new BorrowedBuffer(scores);
        scores[0] = 11;
        System.out.println("borrowed: " + Arrays.toString(borrowed.values()));
        borrowed.values()[1] = 21;
        System.out.println("caller: " + Arrays.toString(scores));

        OwnedBuffer owned = new OwnedBuffer(scores);
        scores[0] = 12;
        System.out.println("owned: " + Arrays.toString(owned.snapshot()));
        int[] exported = owned.snapshot();
        exported[1] = 999;
        System.out.println("owned after export: "
                + Arrays.toString(owned.snapshot()));

        Tag[] original = {new Tag("A")};
        Tag[] shallow = original.clone();
        shallow[0].name = "B";
        System.out.println("shared tag: " + original[0].name);
        shallow[0] = new Tag("C");
        System.out.println("separate slots: "
                + original[0].name + "/" + shallow[0].name);

        String[] names = {"red", "blue"};
        List<String> backed = view(names);
        List<String> frozen = snapshot(names);
        names[0] = "green";
        System.out.println("backed: " + backed);
        System.out.println("snapshot: " + frozen);
        backed.set(1, "black");
        System.out.println("names: " + Arrays.toString(names));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 VarargsOwnershipDemo.java
java VarargsOwnershipDemo
```

Stdout chính xác:

```text
after overwrite: [99, 2]
after rebind: [99, 2]
borrowed: [11, 20]
caller: [11, 21]
owned: [11, 21]
owned after export: [11, 21]
shared tag: B
separate slots: B/C
backed: [green, blue]
snapshot: [red, blue]
names: [green, black]
```

### Đọc những thay đổi trong chương trình

`overwrite` sửa phần tử mảng chung nên `input` thành `[99, 2]`. `rebind` chỉ thay tham chiếu cục bộ nên mảng đó giữ nguyên.

`BorrowedBuffer` giữ mảng `scores` mà không sao chép. Sửa `scores[0]` làm dữ liệu trong buffer đổi theo; sửa phần tử từ getter của buffer lại làm mảng của người gọi đổi theo.

`OwnedBuffer` chụp các giá trị `[11, 21]` lúc được tạo. Việc sửa mảng đầu vào sau đó không làm bản đã lưu đổi. Getter `snapshot` trả bản sao nên việc sửa `exported` cũng không làm dữ liệu nội bộ đổi.

Đây là ví dụ về hai hợp đồng API khác nhau. Giữ mảng dùng chung có thể là thiết kế chủ đích, nhưng tên gọi và tài liệu phải thể hiện rõ trách nhiệm của mỗi bên.

## 5. Sao chép nông chưa tách các đối tượng phần tử

Phần `Tag[]` cho thấy giới hạn của `clone()`:

- Mảng `original` và `shallow` là hai đối tượng mảng khác nhau.
- Hai ô ở chỉ số 0 ban đầu chứa tham chiếu đến cùng một `Tag`.
- Sửa `shallow[0].name` là sửa đối tượng `Tag` dùng chung.
- Gán `shallow[0] = new Tag("C")` chỉ thay ô của mảng sao chép.

Sao chép nông (shallow copy) tách các ô của mảng; nó không tự nhân bản toàn bộ đồ thị đối tượng.

Với mảng nhiều chiều như `int[][]`, sao chép mảng ngoài cũng vẫn dùng chung các mảng con. Nếu cần tách chúng, phải sao chép theo cấu trúc dữ liệu thực sự cần bảo vệ.

Có ba hướng thiết kế thường gặp:

| Dữ liệu | Hướng bảo vệ |
| --- | --- |
| Mảng nguyên thủy | Sao chép mảng đủ để tách các giá trị phần tử |
| Mảng đối tượng bất biến, ví dụ `String[]` | Sao chép mảng để ngăn thay ô; đối tượng phần tử có thể chia sẻ an toàn |
| Mảng đối tượng thay đổi được | Dùng kiểu phần tử bất biến, sao chép từng đối tượng theo hợp đồng, hoặc công bố rõ việc chia sẻ |

Sao chép sâu cần hiểu kiểu phần tử và quan hệ giữa các đối tượng. Không nên hứa “bất biến hoàn toàn” chỉ vì đã gọi một lần `clone()`.

## 6. Làm lộ mảng qua collection

`Arrays.asList(names)` tạo danh sách dựa trên chính mảng đầu vào. Trong chương trình:

- Sửa `names[0]` được nhìn thấy qua `backed`.
- Gọi `backed.set(1, "black")` thay đổi phần tử trong `names`.
- Kích thước danh sách cố định không có nghĩa là nội dung bất biến; `add` hoặc `remove` có thể bị từ chối trong khi `set` vẫn được hỗ trợ.

Bọc danh sách này bằng `Collections.unmodifiableList` chỉ ngăn sửa thông qua lớp bọc. Nếu một bên khác vẫn giữ mảng gốc, họ có thể sửa mảng và dữ liệu nhìn qua lớp bọc vẫn đổi. Đây là chế độ xem không cho sửa, không phải một ảnh chụp độc lập của dữ liệu nguồn.

`List.copyOf(Arrays.asList(names))` trong ví dụ tạo kết quả không bị các lần thay ô sau đó của mảng `names` chi phối. Kết quả cũng không cho phép thêm, xóa hoặc thay phần tử qua API danh sách. Lưu ý:

- `List.copyOf` từ chối collection hoặc phần tử `null`.
- Nó không sao chép sâu các đối tượng phần tử.
- Với phần tử `String` bất biến, chia sẻ tham chiếu phần tử không tạo đường sửa nội dung chuỗi.

Lựa chọn giữa trả mảng sao chép, danh sách sửa được và danh sách không cho sửa phụ thuộc hợp đồng API; không nên lựa chọn chỉ dựa trên số dòng mã.

## 7. Các hậu quả cần dự đoán

### Kết quả tính toán thay đổi ngoài dự kiến

Đối tượng lưu dữ liệu đã xác thực có thể cho kết quả khác sau khi người gọi sửa mảng gốc. Việc tái hiện lỗi khó hơn khi thay đổi diễn ra ở một lớp không liên quan đến chỗ tính toán.

### Thực thi sau và chạy đồng thời

Nếu phương thức lưu mảng để dùng sau, người gọi có thể sửa trước khi công việc thật sự đọc dữ liệu. Hai luồng đọc/ghi cùng mảng mà thiếu đồng bộ còn có thể tạo tranh chấp dữ liệu.

Sao chép khi tiếp nhận dữ liệu giúp tách các lần sửa mảng bên ngoài về sau. Nó không tự làm mọi đối tượng phần tử trở nên an toàn giữa các luồng và không thay thế quy tắc công bố dữ liệu an toàn.

### Lỗi do kiểu mảng thực tế

Một tham số `Object...` không bảo đảm mảng nhận được thật sự có kiểu thời gian chạy `Object[]`. Người gọi có thể truyền một `String[]` làm mảng tham số. Gán một `Integer` vào phần tử của mảng ấy có thể gây `ArrayStoreException`.

Vì vậy, API đọc dữ liệu không nên tự ý ghi các đối tượng tùy ý vào mảng chỉ vì kiểu biến tham số là `Object[]`. Nếu cần vùng làm việc `Object[]`, hãy tạo mảng mới đúng kiểu đó.

## 8. Checklist khi thiết kế phương thức varargs

1. Phương thức chỉ đọc, sửa tại chỗ hay giữ dữ liệu để dùng sau?
2. Người gọi có thể truyền mảng có sẵn không?
3. Có đường trả mảng nội bộ hoặc collection dựa trên mảng ra ngoài không?
4. Cần bảo vệ việc thay ô, nội dung đối tượng phần tử, hay cả hai?
5. Mảng rỗng, mảng null và phần tử null được xử lý thế nào?
6. Có yêu cầu thực thi sau hoặc truy cập từ nhiều luồng không?

Nếu API chỉ đọc trong thời gian gọi, hãy giữ cách triển khai đơn giản và công bố hợp đồng. Nếu đối tượng cần sở hữu trạng thái độc lập, sao chép tại đầu vào và tránh làm lộ trạng thái tại đầu ra.

## 9. Tự kiểm tra

1. `final int... values` có cấm `values[0] = 1` không?
2. Constructor sao chép đầu vào nhưng getter trả trường mảng trực tiếp còn hở chỗ nào?
3. `Tag[] copy = original.clone()` có ngăn sửa `copy[0].name` ảnh hưởng đối tượng gốc không?
4. Vì sao một danh sách kích thước cố định vẫn có thể làm đổi mảng nguồn?
5. `Collections.unmodifiableList(Arrays.asList(array))` có chặn người đang giữ `array` sửa dữ liệu không?

Đáp án:

1. Không; `final` chỉ ngăn gán lại biến tham số.
2. Người gọi getter nhận được mảng nội bộ và có thể sửa phần tử.
3. Không; hai mảng vẫn có thể trỏ đến cùng đối tượng `Tag`.
4. `Arrays.asList` dùng mảng nguồn làm dữ liệu nền; thao tác `set` thay ô mảng.
5. Không; lớp bọc chỉ hạn chế thao tác thông qua chính nó.

## Tài liệu đối chiếu

Xem [JLS 21 §10.7 — Array Members](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html#jls-10.7) về sao chép mảng; [Arrays.asList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)) về danh sách dùng mảng làm dữ liệu nền; và [List.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) về kết quả không cho sửa và giới hạn với phần tử null.
