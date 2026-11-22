# Nhận diện record bằng `isRecord()` và `getRecordComponents()`

Một công cụ tổng quát không phải lúc nào cũng biết trước các kiểu dữ liệu của ứng dụng. Khi nhận `Class<?>`, công cụ có thể cần phân biệt record với lớp thông thường, tìm tên các thành phần dữ liệu và đọc giá trị từ một đối tượng.

Java cung cấp hai điểm bắt đầu: **`isRecord()` xác định kiểu có phải record không**, còn **`getRecordComponents()` mô tả các thành phần được khai báo trong header của record**. Từ mô tả đó, chương trình có thể tìm phương thức truy cập tương ứng để đọc dữ liệu.

Các API này có từ Java 16; ví dụ trong bài dùng Java 17 trở lên, không cần tính năng preview.

## 1. Record và thành phần record là gì?

Xét khai báo:

```java
record Ticket(String title, int priority, boolean ready) {
}
```

`title`, `priority`, `ready` là ba **thành phần record (record component)**. Chúng được khai báo trong phần header giữa hai dấu ngoặc tròn, theo thứ tự đó.

Đối với mỗi thành phần, record có trường dữ liệu tương ứng và một phương thức truy cập công khai. Chẳng hạn, thành phần `title` liên hệ với trường `title` và phương thức `title()`. Đây là quan hệ trong mô hình [record của Java](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html).

Trong Reflection, ba đối tượng có vai trò riêng:

| Đối tượng metadata | Mô tả điều gì? |
| --- | --- |
| `RecordComponent` | Một thành phần trong header của record |
| `Field` | Một trường dữ liệu của lớp |
| `Method` | Một phương thức, gồm cả accessor của record |

`RecordComponent` không phải giá trị `title` của một đối tượng cụ thể. Nó mô tả rằng kiểu record có thành phần tên `title`, kiểu gì và accessor nào.

## 2. Hai API trên `Class<?>`

Chữ ký:

```java
public boolean isRecord()
public RecordComponent[] getRecordComponents()
```

Đây là chữ ký để tra cứu API, không phải các phương thức cần tự cài đặt.

Theo [hợp đồng `Class.getRecordComponents()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getRecordComponents()), mảng kết quả giữ thứ tự khai báo trong header. Nếu là record không có thành phần, mảng có độ dài `0`; nếu không phải record, kết quả là `null`.

| Kiểu đang xét | `isRecord()` | `getRecordComponents()` |
| --- | --- | --- |
| Record có thành phần | `true` | Mảng metadata thành phần |
| Record có header rỗng | `true` | Mảng rỗng |
| Lớp thông thường, interface, enum, kiểu mảng hoặc kiểu nguyên thủy | `false` | `null` |
| Chính lớp cơ sở `java.lang.Record` | `false` | `null` |

Vì vậy, không được gọi `.length` hoặc duyệt trực tiếp kết quả khi chưa xử lý trường hợp `null`. Đồng thời, không xem mảng rỗng như bằng chứng rằng kiểu không phải record.

Bạn có thể kiểm tra `isRecord()` trước để rẽ nhánh theo loại kiểu, hoặc lấy mảng một lần rồi kiểm tra `null`. Trong một công cụ chỉ đọc thành phần record, cách thứ hai thường giúp gom điều kiện và dữ liệu cần dùng vào cùng một chỗ.

## 3. Đọc thông tin từ `RecordComponent`

Mỗi phần tử cung cấp các thông tin sau qua [API `RecordComponent`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html):

| Phương thức | Thông tin nhận được |
| --- | --- |
| `getName()` | Tên thành phần |
| `getType()` | Kiểu được biểu diễn bằng `Class<?>` |
| `getGenericType()` | Kiểu khai báo được biểu diễn bằng `Type`, gồm thông tin generic nếu có |
| `getAccessor()` | Đối tượng `Method` của phương thức truy cập |
| `getDeclaringRecord()` | Lớp record khai báo thành phần |

Ví dụ, với thành phần `List<String> labels`, `getType()` cho `List.class`, còn `getGenericType()` biểu diễn `List<String>`. Metadata kiểu khai báo và giá trị đang chứa trong một đối tượng là hai tầng thông tin khác nhau.

## 4. Thí nghiệm đầy đủ trên Java 17+

Chương trình dưới đây có record có dữ liệu, record rỗng, record generic và một lớp thông thường có cấu trúc gần giống record. Nó vừa đọc metadata của kiểu, vừa đọc giá trị từ đối tượng.

Lưu toàn bộ vào **`RecordInspectionDemo.java`**:

```java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class RecordInspectionDemo {
    public record Ticket(
            String title, int priority, boolean ready, List<String> labels) {
        public static final String KIND = "ticket";
    }

    public record Marker() {
    }

    public record Box<T>(T value) {
    }

    public static final class PlainTicket {
        private final String title;

        public PlainTicket(String title) {
            this.title = title;
        }

        public String title() {
            return title;
        }
    }

    private static void describe(Class<?> type) {
        System.out.println(type.getSimpleName() + " isRecord = " + type.isRecord());
        RecordComponent[] components = type.getRecordComponents();
        if (components == null) {
            System.out.println("components = null");
            return;
        }
        System.out.println("component count = " + components.length);
        for (RecordComponent component : components) {
            System.out.println(component.getName()
                    + " | type=" + component.getType().getTypeName()
                    + " | generic=" + component.getGenericType().getTypeName()
                    + " | accessor=" + component.getAccessor().getName());
        }
    }

    public static Map<String, Object> readRecord(Object value)
            throws ReflectiveOperationException {
        Objects.requireNonNull(value, "value");
        Class<?> type = value.getClass();
        RecordComponent[] components = type.getRecordComponents();
        if (components == null) {
            throw new IllegalArgumentException("Expected record: " + type.getName());
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (RecordComponent component : components) {
            Object componentValue = component.getAccessor().invoke(value);
            result.put(component.getName(), componentValue);
        }
        return result;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        describe(Ticket.class);
        System.out.println("Declared fields, sorted = "
                + Arrays.stream(Ticket.class.getDeclaredFields())
                        .map(field -> field.getName())
                        .sorted()
                        .toList());

        Ticket ticket = new Ticket(
                "Import", 2, true, List.of("java", "reflection"));
        System.out.println("Read values = " + readRecord(ticket));
        System.out.println("First component owner = "
                + Ticket.class.getRecordComponents()[0]
                        .getDeclaringRecord().getSimpleName());
        System.out.println("ready accessor parameters = "
                + Ticket.class.getRecordComponents()[2]
                        .getAccessor().getParameterCount());
        try {
            Ticket.class.getMethod("isReady");
        } catch (NoSuchMethodException ex) {
            System.out.println("isReady lookup = " + ex.getClass().getSimpleName());
        }

        describe(Marker.class);
        System.out.println("Read empty record = " + readRecord(new Marker()));
        describe(PlainTicket.class);
        describe(Record.class);

        describe(Box.class);
        Box<String> box = new Box<>("hello");
        System.out.println("Read generic record = " + readRecord(box));
        System.out.println("Box runtime class = "
                + (box.getClass() == Box.class));

        try {
            readRecord(new PlainTicket("Import"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Read ordinary class = " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror RecordInspectionDemo.java
java RecordInspectionDemo
```

Kết quả:

```text
Ticket isRecord = true
component count = 4
title | type=java.lang.String | generic=java.lang.String | accessor=title
priority | type=int | generic=int | accessor=priority
ready | type=boolean | generic=boolean | accessor=ready
labels | type=java.util.List | generic=java.util.List<java.lang.String> | accessor=labels
Declared fields, sorted = [KIND, labels, priority, ready, title]
Read values = {title=Import, priority=2, ready=true, labels=[java, reflection]}
First component owner = Ticket
ready accessor parameters = 0
isReady lookup = NoSuchMethodException
Marker isRecord = true
component count = 0
Read empty record = {}
PlainTicket isRecord = false
components = null
Record isRecord = false
components = null
Box isRecord = true
component count = 1
value | type=java.lang.Object | generic=T | accessor=value
Read generic record = {value=hello}
Box runtime class = true
Read ordinary class = IllegalArgumentException
```

## 5. Hiểu kết quả của thí nghiệm

### Thứ tự thành phần đến từ header

Header của `Ticket` khai báo `title`, `priority`, `ready`, `labels`. Vòng lặp đi theo đúng thứ tự đó. `priority` không được đưa lên trước chỉ vì kiểu của nó là `int`, và `labels` không được đưa lên đầu theo bảng chữ cái.

Thứ tự này hữu ích khi trình bày cấu trúc dữ liệu, ghép dữ liệu với chữ ký constructor chuẩn hoặc giữ thứ tự cột theo khai báo. Khi dùng metadata cho định dạng lưu trữ lâu dài, vẫn cần quản lý thay đổi cấu trúc; đổi vị trí thành phần trong mã nguồn không phải một thay đổi vô hình đối với công cụ phụ thuộc vào vị trí.

### Trường tĩnh không phải thành phần record

`Ticket` có trường tĩnh `KIND`. Vì vậy, danh sách trường dữ liệu được in trong thí nghiệm gồm `KIND` cùng bốn trường tương ứng các thành phần. Mảng `getRecordComponents()` chỉ có bốn thành phần trong header.

Danh sách trường được **chủ động sắp xếp theo tên** trước khi in, nên dòng `[KIND, labels, priority, ready, title]` không thể được dùng làm bằng chứng về thứ tự mặc định của Reflection.

Nếu mục tiêu là hiểu cấu trúc record, hãy lấy danh sách thành phần trực tiếp. Không lấy tất cả trường rồi tự giả định rằng mọi trường đều là một thành phần hoặc tự dựa vào thứ tự trường.

### Record rỗng và lớp không phải record

`Marker` có header `()` nên `isRecord()` cho `true`, số thành phần bằng `0`, và hàm đọc giá trị tạo bản đồ rỗng `{}`.

`PlainTicket` có một trường `title` và phương thức `title()`, nhưng vẫn là lớp thông thường. Nó không trở thành record chỉ vì đặt tên phương thức theo cùng quy ước. Kết quả là `isRecord()` bằng `false` và mảng thành phần bằng `null`.

`Record.class` cũng cho kết quả tương tự: đây là lớp cơ sở, không phải một record cụ thể có header. Không dùng tên lớp, việc có accessor, hoặc phép kiểm tra kế thừa quá rộng để thay cho `isRecord()`.

## 6. Metadata không tự chứa giá trị của đối tượng

`describe(Ticket.class)` không cần tạo `Ticket`, vì nó chỉ đọc cấu trúc kiểu. Ngược lại, muốn biết `title` đang bằng gì, bạn cần một đối tượng, như biến `ticket` trong ví dụ.

Hàm `readRecord` thực hiện quy trình:

1. Từ chối đối tượng `null`.
2. Lấy lớp thực tế bằng `value.getClass()`.
3. Lấy metadata thành phần và từ chối lớp không phải record.
4. Lấy accessor từ từng `RecordComponent`.
5. Gọi accessor trên đúng đối tượng `value` rồi lưu kết quả theo tên thành phần.

`LinkedHashMap` trong thí nghiệm giữ thứ tự thêm khóa, nên dòng kết quả `Read values` có thứ tự giống header.

Đoạn cốt lõi là:

```java
Object componentValue = component.getAccessor().invoke(value);
```

Đây là đoạn trích trong hàm đã có đầy đủ ở chương trình. `component` là metadata, còn `value` là đối tượng nhận lời gọi. Kiểu trả về của lời gọi động là `Object`; với thành phần nguyên thủy như `int` hoặc `boolean`, kết quả được đóng gói thành đối tượng tương ứng.

### Accessor của record không theo tiền tố JavaBean

`ready` trong ví dụ có accessor `ready()`, không phải `getReady()` hay `isReady()`. Dòng `isReady lookup = NoSuchMethodException` chứng minh không nên tự ghép tiền tố khi tìm accessor mặc định của record.

`getAccessor()` trả đúng `Method` tương ứng, giúp công cụ không phải đoán tên. Quy tắc tên, tham số rỗng và kiểu trả về của accessor được xác định trong [JLS về thành viên record](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.3).

### Gọi accessor vẫn là gọi phương thức

Record có thể khai báo accessor tường minh. Vì vậy, gọi accessor là thực thi hành vi của phương thức đó, không phải luôn đọc trực tiếp trường dữ liệu thô. Công cụ cần hiểu hợp đồng đọc dữ liệu của mình.

Ví dụ dùng record lồng công khai nên có thể gọi accessor mà không mở quyền truy cập đặc biệt. Khi dùng với record từ nơi khác, quyền truy cập lớp, package và module vẫn có thể ảnh hưởng đến lời gọi. Tìm được metadata không tự cấp quyền vượt mọi ranh giới truy cập.

`readRecord` khai báo `throws ReflectiveOperationException` để người gọi biết việc gọi động có thể thất bại. Trong mã thực tế, cần phân biệt lỗi truy cập với ngoại lệ do accessor ném ra và giữ thông tin nguyên nhân; không âm thầm bỏ qua một thành phần khi đọc thất bại.

## 7. Record generic và giới hạn thông tin kiểu

`Box<T>(T value)` cho kết quả:

- `getType()` của `value` là `Object` vì `T` không có giới hạn cụ thể hơn.
- `getGenericType()` biểu diễn biến kiểu `T` trong khai báo.
- Đọc đối tượng `new Box<String>("hello")` cho giá trị `hello`.

Điều đó không có nghĩa metadata của `Box.class` đã đổi `T` thành `String` theo từng đối tượng. Biểu thức `box.getClass() == Box.class` vẫn cho `true`. Cùng một metadata lớp được dùng cho các cách gán tham số kiểu khác nhau của `Box`.

Nếu một thư viện cần biết tham số kiểu cụ thể của ngữ cảnh sử dụng, nó phải nhận thêm thông tin kiểu từ ngữ cảnh đó. Chỉ nhìn vào giá trị đang chứa hoặc vào `getClass()` không phải giải pháp tổng quát để phục hồi toàn bộ thông tin generic.

Phân biệt hai câu hỏi khi thiết kế công cụ:

- Kiểu được **khai báo** của thành phần là gì?
- Giá trị của thành phần trên **đối tượng đang xét** là gì?

Hai câu hỏi bổ sung cho nhau; không thay thế được cho nhau.

## 8. Áp dụng và lỗi thường gặp

Cặp API này phù hợp cho công cụ hiển thị cấu trúc dữ liệu, ánh xạ theo tên thành phần, trình kiểm tra dữ liệu hoặc thư viện cần có một nhánh xử lý riêng cho record. Nó giúp tránh suy luận loại kiểu từ hình dáng lớp.

| Lỗi thường gặp | Cách xử lý đúng |
| --- | --- |
| Gọi `.length` trên kết quả của lớp thông thường | Kiểm tra `null` hoặc rẽ nhánh bằng `isRecord()` |
| Xem record rỗng như không phải record | Phân biệt mảng rỗng với `null` |
| Xem `Record.class` như record cụ thể | Dùng kết quả `isRecord()` |
| Lấy tất cả trường làm thành phần record | Dùng `getRecordComponents()` cho cấu trúc header |
| Tự sắp xếp thành phần rồi nghĩ đó là thứ tự khai báo | Giữ nguyên thứ tự API khi cần thứ tự header |
| Coi `RecordComponent` là dữ liệu của một instance | Dùng accessor trên một đối tượng phù hợp |
| Tự thêm tiền tố `get` hoặc `is` | Dùng `getAccessor()` |
| Cho rằng đọc metadata đồng nghĩa có quyền gọi mọi accessor | Xử lý các ràng buộc truy cập và lỗi gọi động |
| Cho rằng generic của đối tượng đã thay thế `T` trong metadata lớp | Phân biệt kiểu khai báo với ngữ cảnh tham số kiểu |

Record cũng không tự làm toàn bộ cây đối tượng bên trong trở nên bất biến. Nếu một thành phần tham chiếu tới dữ liệu có thể thay đổi, công cụ đọc không nên tự ý sửa dữ liệu đó chỉ vì đã lấy được nó qua accessor.

### Tự kiểm tra

1. Vì sao `Marker.class.getRecordComponents()` cho mảng rỗng, còn `PlainTicket.class.getRecordComponents()` cho `null`?
2. Thêm một trường tĩnh vào `Ticket` có làm số thành phần tăng lên không?
3. Đổi thứ tự `priority` và `ready` trong header ảnh hưởng đến kết quả metadata như thế nào?
4. Vì sao có `Class<?>` đã đủ để mô tả thành phần nhưng chưa đủ để biết giá trị `title`?
5. Với `Box<String>`, tại sao kiểu generic khai báo của `value` vẫn là `T`?

Cần nắm được luồng: **nhận diện record → lấy metadata thành phần theo header → chọn thông tin kiểu hoặc accessor → đọc giá trị trên đúng đối tượng khi cần**.
