# Deconstruction pattern và mục tiêu thiết kế

**Phạm vi:** Java Core Pattern Matching, nhóm Deconstruction. Bài này sử dụng **record patterns**, hình thức giải cấu trúc record được chuẩn hóa trong **Java 21 (JEP 440)**. Ví dụ biên dịch bằng JDK 21 trở lên, không cần bật preview.

## 1. Deconstruction pattern giải quyết vấn đề gì?

Khi một giá trị mang dữ liệu có cấu trúc, một đoạn mã thường cần thực hiện hai việc liên tiếp: **kiểm tra nó thuộc kiểu nào** và **lấy các thành phần cần xử lý**. Cách truyền thống là dùng **instanceof**, tạo một biến cho đối tượng sau khi kiểm tra kiểu, rồi gọi các phương thức truy cập thành phần (accessor).

Giả sử có record:

~~~java
record Size(int width, int height) {}
~~~

Khi nhận một biến kiểu Object, ta có thể viết:

~~~java
if (value instanceof Size size) {
    int width = size.width();
    int height = size.height();
    System.out.println(width + " x " + height);
}
~~~

Java 21 cho phép đặt trực tiếp mẫu giải cấu trúc vào biểu thức kiểm tra:

~~~java
if (value instanceof Size(int width, int height)) {
    System.out.println(width + " x " + height);
}
~~~

Mẫu **Size(int width, int height)** vừa yêu cầu đối tượng phù hợp với record Size, vừa ràng buộc giá trị hai component vào width và height. Nhánh true có thể sử dụng ngay các biến đã ràng buộc.

Đây là mục tiêu cốt lõi: **đưa việc kiểm tra hình dạng dữ liệu và lấy dữ liệu về cùng một vị trí trong mã**, để người đọc thấy rõ những thành phần mà nhánh xử lý cần. Đây không phải cơ chế tạo đối tượng mới, thay thế constructor hay thay đổi trạng thái của record.

Trong Java 21, ta thường gọi hình thức cụ thể này là **record pattern**. Khái niệm **deconstruction pattern** nhấn mạnh hành động lấy thành phần từ một đối tượng; Java 21 không có một cú pháp deconstructor tùy ý áp dụng cho mọi class thông thường.

## 2. Cơ chế của record pattern

Một record có danh sách component được khai báo theo thứ tự:

~~~java
record Size(int width, int height) {}
record Shipment(String id, Size size, int units) {}
~~~

Mẫu tương ứng cũng mô tả các component **theo đúng vị trí**:

~~~java
// Mẫu 1: lấy trực tiếp ba component của Shipment.
if (value instanceof Shipment(var id, var size, var units)) {
    System.out.println(id);
}

// Mẫu 2: tiếp tục giải cấu trúc Size ở component thứ hai.
if (value instanceof Shipment(
        var id, Size(int width, int height), int units)) {
    System.out.println(id + ": " + width + " x " + height);
}
~~~

Các đoạn mã trên là **minh họa cú pháp**: giả định hai record đã được khai báo và value là một biến kiểu Object.

Quá trình khớp có thể hiểu qua bốn bước:

1. Kiểm tra giá trị bên ngoài có khớp kiểu record được chỉ rõ (Shipment) hay không.
2. Lấy các component tương ứng của record thông qua accessor do record cung cấp.
3. Tiếp tục khớp từng component với mẫu con; ở mẫu thứ hai, component **size** phải khớp mẫu record **Size(...)**.
4. Nếu toàn bộ mẫu khớp, các biến **id, width, height, units** được ràng buộc và dùng trong phạm vi mà Java chứng minh mẫu đã khớp.

**var** trong record pattern cho phép trình biên dịch suy luận kiểu của component. Ví dụ, trong **Shipment(var id, var size, var units)**, id có kiểu String, size có kiểu Size, units có kiểu int. Có thể dùng kiểu tường minh như **int width** hoặc **Size(...)** khi điều đó giúp người đọc nhận biết dữ liệu ngay trong mẫu.

**Chú ý tính vị trí:** **Size(int width, int height)** có hai component theo thứ tự khai báo. Đổi tên biến thành **Size(int height, int width)** không làm Java tự đổi vị trí dữ liệu; giá trị đầu tiên vẫn được đưa vào biến đầu tiên. Mẫu không hỗ trợ chọn component bằng tên như cấu trúc ánh xạ key/value. Không thể viết **Size(int width)** cho record gồm hai component.

## 3. Những mục tiêu thiết kế chính

### 3.1. Giảm các bước cơ học trước khi viết logic chính

Khi một nhánh cần nhiều component, record pattern có thể thay các bước lấy object rồi gọi accessor lặp lại. Đoạn mã tập trung vào **giá trị mà nhánh sử dụng**, thay vì các biến trung gian chỉ phục vụ việc bóc tách.

Điều này không có nghĩa mọi lần gọi accessor đều nên đổi sang pattern. Nếu nhánh chỉ cần một component, hoặc còn phải truyền chính object record cho một phương thức khác, type pattern kèm accessor có thể dễ hiểu hơn.

### 3.2. Đưa cấu trúc dữ liệu vào ngay điều kiện quyết định

Mẫu lồng **Shipment(var id, Size(int width, int height), int units)** nêu rõ nhánh cần **một Shipment có một Size ở vị trí thứ hai**. Không cần đọc thân nhánh mới phát hiện điều kiện cấu trúc này.

Mục tiêu ở đây là **tính tường minh của tiền điều kiện về hình dạng dữ liệu**. Nó hữu ích cho các record lồng nhau, đặc biệt khi code xử lý kết quả parser, sự kiện, giá trị trả về phân loại theo kiểu hoặc dữ liệu miền được biểu diễn bằng record.

### 3.3. Kết hợp được với các biểu thức pattern matching khác

Record pattern dùng được với **instanceof** và **switch** hỗ trợ pattern matching trong Java 21. Có thể đặt record pattern vào record pattern khác và phối hợp với điều kiện **when** của switch để diễn đạt lựa chọn xử lý.

Ví dụ:

~~~java
return switch (value) {
    case Shipment(var id, Size(int w, int h), int units)
            when w > 0 && h > 0 && units > 0 ->
            "%s: %dx%d, units=%d".formatted(id, w, h, units);
    case Shipment(var id, var size, var units) ->
            "Invalid shipment: " + id;
    case null -> "No value";
    default -> "Unsupported";
};
~~~

Nhánh đầu diễn đạt **đúng kiểu, đúng cấu trúc và thỏa quy tắc nghiệp vụ**. Nhánh Shipment tiếp theo bao quát các Shipment không đáp ứng điều kiện trước đó; nhánh cuối xử lý kiểu ngoài phạm vi hỗ trợ. Với selector kiểu Object, cần có trường hợp dự phòng; nếu muốn nhận null, hãy xử lý **case null** rõ ràng.

Guard **when** được xét sau khi mẫu trước nó khớp, vì thế **w, h, units** có thể sử dụng trong guard. Nhánh Shipment có guard cụ thể phải đặt trước nhánh Shipment tổng quát; đảo thứ tự có thể khiến nhánh sau bị che khuất và bị trình biên dịch báo lỗi.

### 3.4. Giữ tính an toàn kiểu và phạm vi biến rõ ràng

Trình biên dịch kiểm tra kiểu record, số component và sự tương thích giữa mẫu con và component. Biến pattern chỉ có phạm vi ở những nơi việc khớp được bảo đảm. Trong **if (value instanceof Size(int width, int height))**, width và height khả dụng trong nhánh true; không được tùy tiện dùng chúng sau một đường đi mà mẫu có thể không khớp.

Mục đích của record pattern là **mô tả dữ liệu để ra quyết định**, không phải nới lỏng type checking hoặc ép kiểu không kiểm soát.

## 4. Ví dụ hoàn chỉnh: so sánh cách thủ công và deconstruction pattern

Yêu cầu: nhận một Object. Nếu là Shipment có Size hợp lệ, width và height dương, units dương, trả về mô tả; nếu là Shipment nhưng không đạt điều kiện, trả về thông báo dữ liệu không hợp lệ; đầu vào null và kiểu khác có thông báo riêng.

Lưu toàn bộ mã sau vào **DeconstructionDesignDemo.java**:

~~~java
public class DeconstructionDesignDemo {
    record Size(int width, int height) {}
    record Shipment(String id, Size size, int units) {}

    static String manual(Object value) {
        if (value == null) return "No value";
        if (!(value instanceof Shipment shipment)) return "Unsupported";

        Size size = shipment.size();
        if (size != null
                && size.width() > 0
                && size.height() > 0
                && shipment.units() > 0) {
            return "%s: %dx%d, units=%d".formatted(
                    shipment.id(),
                    size.width(),
                    size.height(),
                    shipment.units());
        }
        return "Invalid shipment: " + shipment.id();
    }

    static String withPatterns(Object value) {
        return switch (value) {
            case Shipment(var id, Size(int w, int h), int units)
                    when w > 0 && h > 0 && units > 0 ->
                    "%s: %dx%d, units=%d".formatted(id, w, h, units);

            case Shipment(var id, var size, var units) ->
                    "Invalid shipment: " + id;

            case null -> "No value";
            default -> "Unsupported";
        };
    }

    public static void main(String[] args) {
        Object[] examples = {
                new Shipment("S-01", new Size(20, 10), 3),
                new Shipment("S-02", null, 2),
                new Shipment("S-03", new Size(0, 10), 1),
                null,
                "text"
        };

        for (Object example : examples) {
            String a = manual(example);
            String b = withPatterns(example);
            System.out.println(b + " | same=" + a.equals(b));
        }
    }
}
~~~

Dùng JDK 21 trở lên:

~~~bash
javac DeconstructionDesignDemo.java
java DeconstructionDesignDemo
~~~

Kết quả:

~~~text
S-01: 20x10, units=3 | same=true
Invalid shipment: S-02 | same=true
Invalid shipment: S-03 | same=true
No value | same=true
Unsupported | same=true
~~~

**Đọc kết quả:**

- **S-01** có đầy đủ Shipment và Size; cả ba điều kiện width, height, units đều dương nên khớp nhánh đầu.
- **S-02** là Shipment có **size = null**. Nó không khớp mẫu **Size(int w, int h)** lồng nhau, rồi khớp nhánh Shipment dự phòng.
- **S-03** có Size không null nhưng width bằng 0: mẫu cấu trúc khớp, **when** không thỏa, nên rơi vào nhánh Shipment dự phòng.
- **null** đi vào **case null**, còn chuỗi **"text"** đi vào **default**.
- Giá trị **same=true** cho cả năm đầu vào chứng minh hai cách triển khai trong ví dụ này đưa ra kết quả như nhau, không phải chứng minh hai cách luôn tương đương trong mọi chương trình.

Điểm cải thiện của record pattern là nhánh đầu cho thấy trực tiếp **Shipment chứa Size với width, height và units cần kiểm tra**; không phải tìm các lời gọi accessor ở phần thân. Sự đánh đổi là mẫu lồng cùng guard có thể dài nếu mô hình phức tạp.

## 5. Deconstruction không đồng nghĩa với kiểm tra tính hợp lệ của dữ liệu

Record pattern diễn đạt **hình dạng và kiểu**, còn quy tắc nghiệp vụ thường cần điều kiện bổ sung.

Ví dụ, **Size(int w, int h)** kiểm tra component size có thể được nhìn như một record Size và lấy w, h. Nó **không tự bảo đảm** w và h dương. Kiểm tra **w > 0 && h > 0** trong guard mới thể hiện yêu cầu đó.

Cũng cần phân biệt **null ở record con** với **null ở component lá**:

- Nếu Shipment có **size = null**, mẫu lồng **Size(int w, int h)** không khớp vì không có record Size để giải cấu trúc.
- Nếu một component tham chiếu được ràng buộc bằng mẫu không điều kiện như **var id** hoặc một type pattern không điều kiện theo kiểu component trong record pattern, giá trị được ràng buộc **vẫn có thể là null**. Đừng suy luận rằng mọi component đều khác null sau khi record pattern khớp.
- Các component nguyên thủy như int không thể nhận null; kiểu bao như Integer hoặc các component tham chiếu có thể null nếu constructor của record cho phép.
- Một record có thể chủ động kiểm tra bất biến trong constructor. Tuy nhiên, bản thân cú pháp deconstruction không tự áp đặt các quy tắc miền đó.

Nếu ứng dụng cần kiểm tra id không rỗng, units ở một khoảng giá trị, hoặc trạng thái giao hàng hợp lệ, hãy dùng điều kiện nghiệp vụ rõ ràng, phương thức có tên thể hiện ý định, hoặc xác lập bất biến phù hợp trong record. Không biến pattern thành một cơ chế validation tưởng tượng.

## 6. Giới hạn và lựa chọn thiết kế

### Chỉ có thể giải cấu trúc record bằng cú pháp record pattern

Cú pháp **SomeRecord(...)** trong Java 21 áp dụng cho kiểu **record** tương thích. Nó không hoạt động cho một class thông thường chỉ vì class đó có getter hoặc constructor với danh sách tham số giống record. Java 21 cũng không cung cấp phép gán phá cấu trúc tùy ý theo dạng một lệnh khai báo nhiều biến từ object.

Record pattern sử dụng cấu trúc component do record khai báo; nó không gọi constructor để tạo bản sao. Với type pattern thông thường, ta lấy biến biểu diễn chính object và có thể gọi accessor khi cần.

### Quyết định dùng pattern dựa vào độ rõ, không dựa vào số dòng

| Trường hợp | Cân nhắc |
| --- | --- |
| Một record đơn giản, cần đọc nhiều component | Record pattern ngắn thường rõ ràng |
| Nhánh chỉ cần một component hoặc toàn bộ object | Type pattern và accessor có thể dễ theo dõi hơn |
| Nhánh phụ thuộc một cấu trúc record lồng nhau ngắn | Nested record pattern giúp trình bày điều kiện ngay tại chỗ |
| Mẫu lồng nhiều cấp với nhiều biến và guard dài | Tách thành bước kiểm tra record con hoặc phương thức riêng |
| Cần phân biệt lý do lỗi của từng component con | Xử lý theo từng bước thay vì gộp mọi trường hợp không khớp |
| Cấu trúc component thay đổi thường xuyên | Cân nhắc việc pattern sẽ liên kết trực tiếp với API component của record |

Một mẫu lồng sâu nhiều cấp có thể làm code khó đọc dù ít dòng. Mục tiêu thiết kế là giúp người đọc nhận ra **vì sao nhánh xử lý áp dụng**, nên tên biến, bố cục và ranh giới của điều kiện quan trọng hơn việc đạt số dòng ngắn nhất.

### Đừng tự động giả định record pattern cải thiện hiệu năng

Cú pháp record pattern trước hết cải thiện **biểu đạt và khả năng kiểm tra kiểu**. Việc nhanh hay chậm phụ thuộc chương trình, hành vi accessor, trình biên dịch và JVM. Không nên chọn record pattern chỉ dựa trên kỳ vọng tăng hiệu năng khi chưa đo đạc.

## 7. Những lỗi thường gặp

1. **Nhầm pattern với constructor:** **Size(int w, int h)** trong instanceof/switch là mẫu, không tạo Size mới.
2. **Nhầm thứ tự component:** record pattern là positional; đổi tên biến không thay đổi component mà chúng nhận.
3. **Thiếu hoặc thừa component:** pattern phải tương ứng với số component của record, kể cả khi chỉ cần dùng một vài giá trị.
4. **Cho rằng record con null vẫn khớp mẫu record con:** **Size(...)** không khớp null; cần nhánh xử lý nếu dữ liệu có thể thiếu.
5. **Cho rằng mọi biến sau giải cấu trúc đều non-null:** các component tham chiếu được ràng buộc bằng pattern không điều kiện có thể vẫn null.
6. **Lẫn kiểm tra cấu trúc với nghiệp vụ:** deconstruction lấy thành phần; các điều kiện dương/âm, giới hạn hoặc tính hợp lệ cần mã kiểm tra riêng.
7. **Sử dụng pattern bên ngoài phạm vi hợp lệ:** biến pattern chỉ được dùng tại nơi chắc chắn khớp; khi đi nhánh false, chúng không mặc nhiên khả dụng.
8. **Đặt case rộng trước case có guard cụ thể:** có thể làm nhánh cụ thể bị che và gây lỗi biên dịch.
9. **Dựa vào default để xử lý selector null:** với switch pattern matching, hãy dùng **case null** khi null là đầu vào cần hỗ trợ.

## 8. Cách tự đánh giá một thiết kế

Trước khi dùng một deconstruction pattern, hãy trả lời các câu hỏi sau: đầu vào có thực sự là record không; nhánh này có cần nhiều component không; việc thấy cấu trúc record ngay tại điều kiện có giúp hiểu nghiệp vụ không; các trường hợp null và sai kiểu đã có đường xử lý rõ chưa; guard có đủ ngắn để đọc ngay không; và việc phụ thuộc vào thứ tự/component của record có chấp nhận được không?

Nếu một pattern khiến mục đích của nhánh rõ hơn, record pattern là lựa chọn tốt. Nếu nó làm lộ quá nhiều chi tiết không liên quan, buộc người đọc đếm dấu ngoặc hoặc trộn lẫn nhiều phép kiểm tra nghiệp vụ, hãy giữ record con trong biến có tên và xử lý theo các bước nhỏ hơn.

**Điều cần nhớ:** mục tiêu thiết kế của deconstruction pattern là kết hợp **kiểm tra kiểu, mô tả cấu trúc và ràng buộc thành phần** thành một cách viết an toàn kiểu, phù hợp với pattern matching của Java. Tính ngắn gọn chỉ có giá trị khi người đọc hiểu điều kiện và hành vi nhanh hơn.