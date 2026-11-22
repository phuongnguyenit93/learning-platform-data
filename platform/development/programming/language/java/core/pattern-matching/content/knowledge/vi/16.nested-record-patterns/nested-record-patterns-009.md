# Giới hạn độ sâu để giữ tính dễ đọc

**Chủ đề:** Nested record patterns trong Java Core Pattern Matching. **Phiên bản:** Java 21 trở lên (record patterns được chuẩn hóa ở Java 21, JEP 440; không cần bật preview).

Record pattern giúp kiểm tra một giá trị có đúng kiểu record và lấy ngay các component của record đó. Khi record chứa record khác, ta có thể đặt các mẫu bên trong nhau. Cách viết này rất gọn khi hình dạng dữ liệu là điều kiện quan trọng, nhưng nếu lồng quá sâu, người đọc phải lần theo nhiều dấu ngoặc và tên biến trước khi thấy mục đích xử lý.

**Nguyên tắc chính:** Chỉ lồng đến mức mà cấu trúc còn giúp giải thích điều kiện. Khi các cấp sâu bắt đầu che nghiệp vụ, hãy dừng giải cấu trúc, giữ một biến record trung gian rồi xử lý tiếp ở dòng hoặc phương thức có tên rõ ràng.

## 1. Độ sâu của nested record pattern nghĩa là gì?

Giả sử có ba record:

~~~java
record Address(String city, String street) {}
record Customer(String name, Address address) {}
record Order(String id, Customer customer, int totalCents) {}
~~~

Một mẫu đầy đủ đi qua ba record:

~~~java
if (value instanceof Order(
        var id,
        Customer(
                var name,
                Address(var city, var street)),
        var totalCents)) {
    // Đã có id, name, city, street, totalCents.
}
~~~

Nếu đếm các lớp record từ ngoài vào trong, **Order là cấp 1**, **Customer là cấp 2**, **Address là cấp 3**. Mẫu cho biết cả đường đi Order → Customer → Address phải khớp. Chỉ sau đó các biến trong nhánh true mới có hiệu lực.

Java không quy định một ngưỡng “tối đa hai cấp” để bảo đảm tính dễ đọc. Giới hạn độ sâu trong bài này là **quy ước thiết kế**, không phải luật cú pháp hay một ràng buộc của trình biên dịch. Một mẫu ba cấp ngắn có thể tốt, trong khi một mẫu hai cấp với nhiều nhánh và điều kiện rối vẫn khó hiểu.

Số cấp chỉ là tín hiệu để xem lại mã. Hãy đánh giá cùng lúc **độ dài biểu thức**, **số biến được trích xuất**, **các điều kiện đi kèm**, **cách xử lý null** và **mục tiêu nghiệp vụ**.

## 2. Tại sao mẫu lồng sâu làm giảm tính dễ đọc?

Với mẫu Order(Customer(Address(...))), người đọc thường phải thực hiện các bước sau: nhận diện loại đối tượng đầu vào; xác định Customer nằm ở component nào của Order; tìm Address thuộc Customer; xem tên các biến cần dùng; rồi mới đọc điều kiện hoặc hành động phía sau.

Việc lồng sâu dễ gây ra một số vấn đề:

- **Mất trọng tâm:** logic quan trọng, ví dụ kiểm tra đơn hàng đủ điều kiện, bị đẩy ra sau một cấu trúc trích xuất dữ liệu dài.
- **Khó nhận biết trường hợp không khớp:** chỉ cần một record con được yêu cầu bởi mẫu mà là null, toàn bộ mẫu đó không khớp; một nhánh dự phòng chung có thể che mất lý do cụ thể.
- **Nhiều tên biến sống trong cùng phạm vi:** dễ nhầm customerName với receiverName, sourceCity với destinationCity hoặc số tiền của các cấp khác nhau.
- **Thay đổi cấu trúc gây sửa lan rộng:** khi thay cách tổ chức component, nhiều nhánh có mẫu lồng sâu phải thay đổi cùng lúc.
- **Khó rà soát điều kiện:** biểu thức ghép mẫu nhiều cấp với các phép so sánh, toán tử logic hoặc điều kiện **when** dài sẽ rất khó đọc.

Một biểu thức ngắn dòng chưa chắc dễ hiểu. Khi các thành phần có tên tốt và được căn lề theo cấp, mẫu hai hoặc ba cấp vẫn có thể rõ hơn việc gọi nhiều accessor. Cần chọn theo nhiệm vụ của đoạn mã.

## 3. Ví dụ trước và sau: hai cách xử lý cùng dữ liệu

Yêu cầu: nếu đầu vào là Order có Customer và Address hợp lệ về mặt cấu trúc, xuất tóm tắt gồm mã đơn, tên khách, thành phố, đường phố, số tiền. Nếu thiếu bất kỳ record nào trong đường lồng đó, trả về **Missing nested data**.

### Cách A — giải cấu trúc ba cấp ngay trong một mẫu

~~~java
static String deep(Object value) {
    if (value instanceof Order(
            var id,
            Customer(var name, Address(var city, var street)),
            var totalCents)) {
        return render(id, name, city, street, totalCents);
    }
    return "Missing nested data";
}
~~~

Ưu điểm: rất ngắn; chỉ một điều kiện đã diễn tả hình dạng bắt buộc. Thích hợp khi mọi component cần được đọc ngay và nhánh hành động đơn giản.

Hạn chế: nếu thêm nhiều record lồng nữa hoặc nhiều quy tắc nghiệp vụ, biểu thức tăng độ phức tạp nhanh. Không thể phân biệt ngay nhánh không khớp vì thiếu Customer hay thiếu Address, trừ khi bổ sung nhánh khác.

### Cách B — dừng ở mỗi ranh giới record và xử lý theo bước

~~~java
static String stepwise(Object value) {
    if (!(value instanceof Order(var id, var customer, var totalCents))) {
        return "Missing nested data";
    }
    if (!(customer instanceof Customer(var name, var address))) {
        return "Missing nested data";
    }
    if (!(address instanceof Address(var city, var street))) {
        return "Missing nested data";
    }
    return render(id, name, city, street, totalCents);
}
~~~

Ở đây mỗi lần đọc chỉ phải hiểu **một record pattern**. Tên customer và address giúp làm lộ ranh giới nghiệp vụ: đơn hàng, khách hàng, địa chỉ. Nếu cần bổ sung kiểm tra customer hoặc address ở từng tầng, có thể đặt đúng tại nơi dữ liệu trở nên sẵn sàng.

Nhờ **flow scoping** của Java, các biến ràng buộc bởi pattern trong điều kiện phủ định vẫn có thể dùng ở đoạn phía sau nếu nhánh không khớp đã **return**. Trong ví dụ, id, customer và totalCents có hiệu lực sau if đầu tiên; name và address có hiệu lực sau if thứ hai.

Lưu ý: một biến **var** trong record pattern có thể mang giá trị null của component tham chiếu; do đó cách B cần kiểm tra record con bằng instanceof ở bước tiếp theo. Trong cách A, mẫu Customer(...) hoặc Address(...) lồng vào sẽ không khớp nếu chính record con đó là null.

Hai cách có thể cho **cùng kết quả nghiệp vụ** nếu giữ nguyên các điều kiện và nhánh dự phòng. Việc tách mẫu không tự động thay đổi yêu cầu chấp nhận dữ liệu.

## 4. Chương trình Java 21 hoàn chỉnh, có thể chạy

Lưu toàn bộ mã sau thành **PatternDepthDemo.java**. Chương trình dùng hai cách đã phân tích và in cùng một kết quả cho các trường hợp tương ứng.

~~~java
public class PatternDepthDemo {
    record Address(String city, String street) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer, int totalCents) {}

    private static String render(String id, String name, String city,
                                 String street, int totalCents) {
        return "%s | %s | %s/%s | %d".formatted(
                id, name, city, street, totalCents);
    }

    static String deep(Object value) {
        if (value instanceof Order(
                var id,
                Customer(var name, Address(var city, var street)),
                var totalCents)) {
            return render(id, name, city, street, totalCents);
        }
        return "Missing nested data";
    }

    static String stepwise(Object value) {
        if (!(value instanceof Order(var id, var customer, var totalCents))) {
            return "Missing nested data";
        }
        if (!(customer instanceof Customer(var name, var address))) {
            return "Missing nested data";
        }
        if (!(address instanceof Address(var city, var street))) {
            return "Missing nested data";
        }
        return render(id, name, city, street, totalCents);
    }

    public static void main(String[] args) {
        Object good = new Order(
                "ORD-17", new Customer(
                        "An", new Address("Da Nang", "Bach Dang")), 99000);
        Object missing = new Order(
                "ORD-18", new Customer("Binh", null), 50000);

        System.out.println(deep(good));
        System.out.println(stepwise(good));
        System.out.println(deep(missing));
        System.out.println(stepwise(missing));
        System.out.println(stepwise(null));
    }
}
~~~

Biên dịch và chạy với JDK 21+:

~~~bash
javac PatternDepthDemo.java
java PatternDepthDemo
~~~

Đầu ra chính xác:

~~~text
ORD-17 | An | Da Nang/Bach Dang | 99000
ORD-17 | An | Da Nang/Bach Dang | 99000
Missing nested data
Missing nested data
Missing nested data
~~~

**Giải thích:** good có đủ Order, Customer và Address nên hai cách trả về chuỗi giống nhau. Với missing, component address là null: cách A thất bại khi cần khớp Address(...), còn cách B đi qua Order và Customer nhưng thất bại ở kiểm tra address instanceof Address(...). Selector null trong instanceof trả về false, vì vậy stepwise(null) cũng đi đến nhánh dự phòng. Ví dụ dùng thông báo chung để dễ so sánh; chương trình thực tế có thể tách riêng nguyên nhân thiếu customer và thiếu address.

Các kiểu String dùng **var** ở phần lá có thể giữ null; phương thức formatted có thể in ra chữ **null** trong trường hợp đó. Khớp một record pattern **không đồng nghĩa** mọi trường dữ liệu bên trong đều thỏa ràng buộc nghiệp vụ. Nếu name, city hay street bắt buộc không rỗng, cần kiểm tra rõ ràng ở nơi thích hợp.

## 5. Đặt ranh giới lồng ở đâu?

Một nguyên tắc thực hành: **ưu tiên một hoặc hai cấp nếu ý nghĩa vẫn rõ**; khi lên cấp ba hoặc sâu hơn, chủ động cân nhắc tách bước. Đây là lời nhắc kiểm tra readability, không phải quy tắc bắt buộc. Hãy dùng bảng dưới đây để quyết định.

| Dấu hiệu trong bài toán | Cách viết thường rõ hơn | Lý do |
| --- | --- | --- |
| Cần lấy vài component ngay từ một record | Một record pattern đơn | Hiện rõ kiểu và giá trị cần dùng |
| Hai record lồng nhau, nhánh xử lý đơn giản | Nested record pattern hai cấp | Hình dạng dữ liệu giúp đọc điều kiện nhanh |
| Ba cấp nhưng mẫu ngắn, tên biến rõ, không nhiều rẽ nhánh | Có thể giữ mẫu lồng | Ít thao tác trung gian hơn mà vẫn theo dõi được |
| Ba cấp trở lên kèm nhiều điều kiện nghiệp vụ | Tách theo từng cấp | Tách kiểm tra cấu trúc ra khỏi luật nghiệp vụ |
| Cần trả lỗi khác nhau khi thiếu Customer hoặc Address | Tách thành nhiều if/nhánh | Dễ chỉ rõ điểm dữ liệu không đạt |
| Cùng cấu trúc được đọc ở nhiều nhánh/phương thức | Trích phương thức có tên phù hợp | Giảm lặp và gom quy tắc vào một nơi |
| Chỉ cần một giá trị đơn lẻ | Type pattern hoặc accessor | Giải cấu trúc toàn bộ có thể là thừa |
| Cần dùng chính object con trong nhiều thao tác | Giữ biến record con | Không phải ghép lại thông tin từ các biến lá |

Có thể tự đặt câu hỏi: người đọc có hiểu đoạn này trong một lượt nhìn mà không phải đếm dấu ngoặc hoặc đọc ngược các tên component không? Nếu không, nên tách.

## 6. Làm rõ điều kiện nghiệp vụ khi mẫu bắt đầu dài

Giả sử chỉ xử lý đơn hàng có số tiền dương và địa chỉ thuộc thành phố được hỗ trợ. Không cần đưa mọi quy tắc vào cùng điều kiện giải cấu trúc:

~~~java
// Đoạn minh họa: sử dụng các record Order, Customer, Address đã khai báo.
static boolean supportedCity(String city) {
    return "Da Nang".equals(city) || "Ha Noi".equals(city);
}

static boolean eligible(Object value) {
    if (!(value instanceof Order(var id, var customer, var totalCents))) {
        return false;
    }
    if (!(customer instanceof Customer(var name, var address))) {
        return false;
    }
    if (!(address instanceof Address(var city, var street))) {
        return false;
    }

    return totalCents > 0 && supportedCity(city);
}
~~~

Ở bản này, **ba bước đầu** kiểm tra hình dạng record cần thiết; dòng return cuối thể hiện luật nghiệp vụ. Phương thức supportedCity mang tên mô tả mục đích và dùng so sánh an toàn khi city là null. Các biến id, name và street đang chưa dùng trong hàm; nếu thực sự không cần trích các component đó, có thể chọn cách dùng một type pattern cùng accessor hoặc dùng biến đặt tên gọn hơn. Không nên cố giữ mẫu record cho mọi trường hợp.

Khi sử dụng **switch** với record pattern và guard **when**, cũng áp dụng cùng nguyên tắc. Guard ngắn như **when totalCents > 0** có thể hỗ trợ đọc nhanh; guard dài kết hợp nhiều phép toán, gọi hàm và các mẫu record nhiều cấp thường nên được tách thành phương thức với tên thể hiện quy tắc. Đồng thời nhớ sắp xếp nhánh cụ thể trước nhánh tổng quát nếu không muốn bị pattern rộng hơn che khuất.

## 7. Giữ nguyên hành vi khi refactor từ mẫu sâu sang mẫu nông

Tách pattern là một thay đổi về cách tổ chức code; vẫn cần kiểm tra các trường hợp cạnh tranh nhau:

1. **Sai kiểu ở ngoài cùng:** Object không phải Order phải đi đúng nhánh từ chối.
2. **Record con null:** Order có customer = null hoặc Customer có address = null phải đi đúng nhánh tương ứng. Mẫu record con được lồng không khớp với null.
3. **Component lá null:** Tùy dùng **var** hay pattern có kiểu và quy tắc kiểm tra đi kèm, cần bảo toàn ý nghĩa của null; không mặc định record đồng nghĩa non-null ở mọi component.
4. **Guard và thứ tự nhánh:** Với switch, điều kiện cụ thể và thứ tự case phải giữ đúng ý nghĩa ban đầu.
5. **Giá trị trả về và đường đi lỗi:** Không được biến một đầu vào từng bị từ chối thành đầu vào được chấp nhận chỉ vì đã chuyển một bước kiểm tra.
6. **Phạm vi biến:** Biến pattern chỉ có thể được sử dụng khi trình biên dịch chứng minh mẫu đã khớp; các biến sau nhánh return trong ví dụ là một trường hợp hợp lệ.

Đừng đổi một mẫu lồng sâu thành chuỗi accessor bằng cách quên kiểm tra null:

~~~java
// Cần bảo đảm customer() và address() khác null trước khi gọi tiếp.
String city = order.customer().address().city();
~~~

Dòng trên có thể ném **NullPointerException** nếu customer hoặc address là null. Một mẫu lồng sâu trong instanceof sẽ không khớp khi record con tương ứng là null; hai cách chỉ tương đương khi kiểm soát đúng các nhánh null.

## 8. Checklist cho code review

Trước khi chốt một nested record pattern, hãy kiểm tra:

- **Mục đích:** mẫu thể hiện cấu trúc dữ liệu cần quyết định, hay đang che mất nghiệp vụ?
- **Độ sâu:** có thể hiểu đường đi record cha → record con ngay, không cần lần theo nhiều tầng?
- **Tên biến:** tên có thể đọc độc lập như billingCity, shippingCity, customerName?
- **Điều kiện:** pattern và guard có thể đọc trong một nhịp, hay nên tách phương thức?
- **Null:** record con null và component lá null được xử lý đúng yêu cầu?
- **Tính lặp:** cùng một cấu trúc giải cấu trúc có bị sao chép ở nhiều nơi?
- **Độ tương đương:** sau khi tách, các trường hợp thành công và thất bại có giữ nguyên kết quả?

Nếu mẫu lồng giúp diễn tả ngay dữ liệu bắt buộc và nhánh hành động ngắn, cứ giữ nó. Nếu độ sâu buộc người đọc giải mã cấu trúc trước khi hiểu nghiệp vụ, hãy **dừng pattern ở một record có tên rõ ràng**, kiểm tra tiếp theo từng bước và để điều kiện nghiệp vụ ở dòng hoặc phương thức riêng. Đó là giới hạn độ sâu phục vụ tính dễ đọc trong Java, chứ không phải một ngưỡng cú pháp cứng.