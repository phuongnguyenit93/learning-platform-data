# Chọn giữa pattern và polymorphism

## 1. Hai cách giải quyết khác nhau, không phải đối thủ tuyệt đối

Khi làm việc với một kiểu cha có nhiều kiểu con, Java cho phép hai hướng xử lý:

- **Polymorphism (đa hình):** gửi cùng một thông điệp đến đối tượng qua phương thức của interface/class cha; kiểu cụ thể tự quyết định cách thực hiện. Code gọi thường không phải kiểm tra đối tượng thuộc subtype nào.
- **Pattern matching:** kiểm tra một giá trị có thuộc kiểu hoặc cấu trúc cần xử lý không, có thể ràng buộc các biến và chọn hành động tương ứng. Java 21 hỗ trợ type patterns, record patterns và pattern matching trong `switch`.

Ví dụ domain giao hàng gồm `Courier` (giao tận nhà) và `Pickup` (nhận tại điểm). Có hai câu hỏi khác nhau:

1. “Một phương thức giao hàng tính phí của nó thế nào?” — đây có thể là **hành vi cốt lõi** thuộc về từng kiểu giao hàng, phù hợp với polymorphism.
2. “Màn hình quản trị muốn hiển thị mô tả khác nhau theo từng cấu trúc giao hàng như thế nào?” — đây có thể là **phép phân loại và chuyển đổi dữ liệu** phục vụ một ngữ cảnh cụ thể, phù hợp với pattern matching.

**Nguyên tắc lựa chọn:** Không chọn cách nào chỉ vì nó ít dòng hơn. Hãy hỏi: **logic thuộc trách nhiệm của chính đối tượng hay của bên đang quan sát/phân loại đối tượng?**, và **tập subtype có cần mở rộng độc lập hay không?**

## 2. Polymorphism: hành vi nằm ở đối tượng

Giả sử mô hình:

```java
sealed interface Delivery permits Courier, Pickup {
    int fee();
}

record Courier(int distanceKm) implements Delivery {
    @Override
    public int fee() {
        return 10 + 2 * distanceKm;
    }
}

record Pickup(String stationCode) implements Delivery {
    @Override
    public int fee() {
        return 5;
    }
}
```

Đây là các khai báo Java 17+ minh họa; ví dụ hoàn chỉnh ở phần sau bổ sung validation.

Người dùng interface chỉ việc gọi:

```java
static int calculateFee(Delivery delivery) {
    return delivery.fee();
}
```

Không cần viết:

```java
// Cách phân loại kiểu để gọi lại hành vi của từng subtype:
// thường làm logic phụ thuộc trực tiếp vào các kiểu cụ thể.
static int calculateFeeVerbose(Delivery delivery) {
    if (delivery instanceof Courier courier) {
        return courier.fee();
    }
    if (delivery instanceof Pickup pickup) {
        return pickup.fee();
    }
    throw new IllegalArgumentException("Unknown delivery");
}
```

Nếu hai subtype đều đã triển khai `fee()`, việc kiểm tra kiểu chỉ để gọi `fee()` trên từng subtype là **dư thừa**. Nó khiến code phía ngoài phải biết mọi loại giao hàng, dù interface đã cung cấp đúng hợp đồng để che giấu khác biệt ấy.

### Ưu điểm của đa hình

- **Tập trung hành vi:** công thức phí của `Courier` nằm trong `Courier`, công thức của `Pickup` nằm trong `Pickup`; các caller chỉ phụ thuộc `Delivery.fee()`.
- **Dễ mở rộng subtype trong hệ mở:** với interface thông thường, thêm implementation mới có thể không đòi hỏi sửa những nơi chỉ gọi phương thức chung, miễn implementation tuân thủ hợp đồng.
- **Đóng gói invariant:** mỗi implementation có thể tự xác nhận dữ liệu đầu vào và cách tính; tránh việc nhiều caller tái triển khai cùng quy tắc.
- **Dễ gọi và test qua hợp đồng:** code dùng `Delivery` không cần biết quá nhiều chi tiết bên trong subtype.

### Giới hạn của đa hình

Nếu có một **tác vụ mới, độc lập với bản chất domain** — chẳng hạn kết xuất một định dạng báo cáo đặc thù, tạo nhãn giao diện hoặc xuất một định dạng dành riêng cho hệ thống đối tác — đặt thêm phương thức vào interface có thể khiến mọi subtype mang trách nhiệm không cần thiết.

Mỗi lần thêm một **phương thức trừu tượng** vào interface đang được nhiều đơn vị triển khai, các implementation hiện có thường phải cập nhật khi biên dịch lại. `default method` có thể giảm tác động trong một số trường hợp, nhưng không giải quyết mọi vấn đề thiết kế hay tương thích. Nếu mỗi màn hình muốn có một phương thức riêng trên domain type, mô hình dễ bị phình to.

## 3. Pattern matching: phân loại từ góc nhìn của thao tác

Với Java 21, một phép chuyển đổi dữ liệu có thể viết bằng `switch expression`:

```java
static String label(Delivery delivery) {
    return switch (delivery) {
        case Courier(int distanceKm) when distanceKm > 10 ->
                "Giao xa: " + distanceKm + " km";
        case Courier(int distanceKm) ->
                "Giao tận nhà: " + distanceKm + " km";
        case Pickup(String stationCode) ->
                "Nhận tại điểm " + stationCode;
        case null ->
                "Chưa chọn phương thức";
    };
}
```

Ở đây `label` thuộc **ngữ cảnh hiển thị**, không phải quy tắc tính phí. Nó quan sát record và trích xuất những component cần dùng:

- `Courier(int distanceKm)` kiểm tra kiểu và lấy khoảng cách từ component của record.
- `when distanceKm > 10` là **guard** được đánh giá sau khi pattern khớp. Case chi tiết được đặt trước case `Courier` không có guard để tránh bị nhánh rộng hơn bao phủ.
- `Pickup(String stationCode)` phân rã mã điểm nhận hàng.
- `case null` xử lý selector `null` riêng, thay vì để chương trình vô tình ném `NullPointerException`.

Vì `Delivery` trong ví dụ là **sealed interface** chỉ có hai subtype trực tiếp `Courier` và `Pickup`, và cả hai đều là record final, compiler Java 21 có thể kiểm tra hai loại không-null đã được bao phủ bởi những case không guard. Ở ví dụ này không cần `default`.

**Điểm mạnh của pattern matching:** những phép chuyển đổi có quan điểm của bên ngoài có thể được bổ sung trong lớp báo cáo, adapter hoặc phần giao diện mà không bắt các domain record biết đến mọi ngữ cảnh tiêu thụ chúng. Một `switch` gọn còn làm rõ toàn bộ tập kết quả cạnh nhau.

**Điểm yếu:** nếu nhiều module cùng viết `switch` để tính lại một quy tắc nghiệp vụ chung theo từng subtype, quy tắc dễ bị sao chép và lệch nhau. Pattern matching không tự thay thế trách nhiệm đóng gói hành vi.

## 4. Vì sao sealed interface làm thay đổi phép so sánh?

`sealed interface` và `interface` thông thường là một **quyết định độc lập nhưng liên quan mạnh** đến lựa chọn pattern hay polymorphism.

### Domain đóng hoặc được kiểm soát

`sealed interface Delivery permits Courier, Pickup` quy định các subtype trực tiếp có thể triển khai kiểu gốc. Khi tất cả nhánh đã biết, một `switch expression` liệt kê các type/record pattern có thể được compiler kiểm tra **exhaustiveness**.

Nếu sau này người sở hữu domain thêm `Drone` vào `permits`, các `switch` không có nhánh bao quát có thể bị báo thiếu case khi biên dịch lại, buộc người phát triển xác định xử lý `Drone` trong từng tác vụ. Đây có thể là ưu điểm: thay đổi domain tạo tín hiệu rõ ở các nơi phân loại.

Không nên thêm `default` vào mọi `switch` của hierarchy đóng chỉ để im lặng trước subtype mới. `default` thường che đi cơ hội được compiler nhắc cập nhật một chính sách cần xử lý đầy đủ.

### Domain mở cho plugin

Ví dụ:

```java
interface DeliveryPlugin {
    String providerName();
}
```

Không thể biết trước mọi implementation sẽ được đối tác cung cấp. Khi xử lý một `DeliveryPlugin`, cách gọi hành vi qua interface thường có lợi:

```java
static String provider(DeliveryPlugin plugin) {
    return plugin.providerName();
}
```

Một `switch` cố liệt kê vài implementation cụ thể của interface mở cần có cách xử lý các implementation khác. Code dựa vào `case SomePlugin`, `case OtherPlugin` rất dễ phụ thuộc sai vào danh sách hiện tại. Nếu một bên thứ ba có thể thêm loại mới không báo trước, polymorphism thường bảo vệ phần lớn caller tốt hơn việc liệt kê subtype.

**Lưu ý:** Không phải cứ sealed thì bắt buộc phải dùng switch; một sealed interface vẫn hoàn toàn có thể khai báo phương thức đa hình. Ngược lại, `instanceof` và type pattern vẫn dùng được với interface mở. Sealed chỉ cung cấp thêm thông tin cho type system về **tập subtype được phép**.

## 5. Chọn theo chiều thay đổi: thêm subtype hay thêm thao tác?

Có thể nhìn sự phát triển của domain theo hai chiều:

| Thay đổi trong tương lai | Thiết kế ưu tiên polymorphism | Thiết kế ưu tiên pattern/switch |
| --- | --- | --- |
| **Thêm subtype** | Nếu interface mở và hợp đồng hành vi ổn định, kiểu mới tự triển khai các phương thức; caller chung thường giữ nguyên. | Các `switch` liệt kê subtype có thể cần thêm case; ở sealed hierarchy, compiler giúp phát hiện nhiều vị trí thiếu. |
| **Thêm thao tác mới** | Nếu thao tác thuộc hợp đồng, thường cần thêm phương thức và implement ở các subtype (hoặc thiết kế khác để tránh phình interface). | Có thể thêm một hàm `switch` độc lập trong module tiêu thụ, không cần sửa từng subtype. |
| **Sửa quy tắc nghiệp vụ chung** | Quy tắc ở từng implementation; caller không phải sao chép logic. | Nếu quy tắc bị rải ở nhiều `switch`, dễ phải sửa nhiều nơi. |
| **Đọc nhiều biến thể của dữ liệu đóng** | Có thể dùng hành vi chung hoặc Visitor nếu phù hợp. | Pattern matching ngắn gọn, rõ nhánh; đặc biệt hữu ích với record và sealed. |
| **Cho phép plugin độc lập** | Hợp đồng đa hình của interface mở thường thuận lợi hơn. | Liệt kê type cụ thể khó theo kịp plugin mới; cần nhánh tổng quát/fallback. |

Đây là **đánh đổi về tổ chức code**, không phải công thức có nghiệm duy nhất. Trường hợp có **nhiều subtype thường xuyên được thêm** nhưng **ít thao tác ổn định** nghiêng về polymorphism. Trường hợp có **tập subtype đóng, ít đổi** nhưng **nhiều thao tác đọc dữ liệu độc lập** nghiêng về pattern matching hoặc cách tổ chức dữ liệu định hướng thao tác.

Ví dụ một AST của compiler thường gồm tập node được kiểm soát; nhiều bước xử lý như in cây, phân tích, sinh mã có thể cần truy cập cấu trúc theo từng loại node. Ngược lại, hợp đồng cho một plugin exporter thường cần cho phép implementation mới mà code gọi không bị buộc phải nhận diện từng plugin.

## 6. Ví dụ Java 21 chạy hoàn chỉnh: kết hợp cả hai

Để so sánh cùng kết quả, chương trình dưới đây cố ý có cả `fee()` đa hình và `feeByPattern()` tính phí bằng `switch`. **Trong sản phẩm thật không nên duy trì hai bản sao công thức tính phí**. Hàm `feeByPattern()` ở đây chỉ giúp quan sát hai lựa chọn; sau khi quyết định thiết kế, hãy giữ **một nguồn sự thật** cho quy tắc phí. Hàm `label()` là ví dụ hợp lý để giữ pattern matching cho riêng nghiệp vụ trình bày.

Tạo tệp **`PatternVsPolymorphismDemo.java`**:

```java
public class PatternVsPolymorphismDemo {
    sealed interface Delivery permits Courier, Pickup {
        int fee();
    }

    record Courier(int distanceKm) implements Delivery {
        Courier {
            if (distanceKm < 0) {
                throw new IllegalArgumentException("distanceKm must be >= 0");
            }
        }

        @Override
        public int fee() {
            return 10 + 2 * distanceKm;
        }
    }

    record Pickup(String stationCode) implements Delivery {
        Pickup {
            java.util.Objects.requireNonNull(stationCode, "stationCode");
        }

        @Override
        public int fee() {
            return 5;
        }
    }

    // Minh hoa phuong an thay the: switch lam phep tinh phi.
    static int feeByPattern(Delivery delivery) {
        return switch (delivery) {
            case Courier(int distanceKm) -> 10 + 2 * distanceKm;
            case Pickup(String stationCode) -> 5;
            case null -> throw new IllegalArgumentException("Missing delivery");
        };
    }

    // Ngu canh hien thi: dung pattern de lay du lieu tung record.
    static String label(Delivery delivery) {
        return switch (delivery) {
            case Courier(int distanceKm) when distanceKm > 10 ->
                    "Giao xa: " + distanceKm + " km";
            case Courier(int distanceKm) ->
                    "Giao tận nhà: " + distanceKm + " km";
            case Pickup(String stationCode) ->
                    "Nhận tại điểm " + stationCode;
            case null ->
                    "Chưa chọn phương thức";
        };
    }

    static void show(Delivery delivery) {
        System.out.println(label(delivery));
        System.out.println("Phí đa hình: " + delivery.fee());
        System.out.println("Phí pattern: " + feeByPattern(delivery));
    }

    public static void main(String[] args) {
        show(new Courier(4));
        show(new Pickup("P-01"));
        show(new Courier(12));
        System.out.println(label(null));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên** (không cần `--enable-preview`):

```bash
javac -encoding UTF-8 PatternVsPolymorphismDemo.java
java PatternVsPolymorphismDemo
```

Kết quả:

```text
Giao tận nhà: 4 km
Phí đa hình: 18
Phí pattern: 18
Nhận tại điểm P-01
Phí đa hình: 5
Phí pattern: 5
Giao xa: 12 km
Phí đa hình: 34
Phí pattern: 34
Chưa chọn phương thức
```

Giải thích từng trường hợp:

1. `new Courier(4)` là kiểu giao tận nhà, nên `fee()` trả `10 + 2 * 4 = 18`. `feeByPattern()` khớp record `Courier` và cho cùng kết quả. Trong `label()`, `distanceKm > 10` sai nên chọn case `Courier` còn lại.
2. `new Pickup("P-01")` có phí cố định `5` theo cả hai cách. Pattern `Pickup(String stationCode)` lấy mã điểm nhận hàng để tạo nhãn riêng.
3. `new Courier(12)` có phí `34`; vì `12 > 10`, case có `when` tạo nhãn “Giao xa”.
4. `label(null)` trả “Chưa chọn phương thức”. Hàm `show` chỉ được gọi với đối tượng khác null; nếu gọi `delivery.fee()` trên null, Java sẽ ném `NullPointerException`, còn `feeByPattern(null)` được thiết kế ném `IllegalArgumentException`. Hai cách xử lý null khác nhau này là lựa chọn API, **không phải tính chất bắt buộc của pattern hay polymorphism**. Muốn so sánh hoặc refactor tương đương, cần thống nhất hợp đồng null trước.

Ở mẫu này, `Courier` có constructor kiểm tra khoảng cách không âm, `Pickup` yêu cầu mã điểm nhận hàng khác null. Record patterns có các component kiểu cụ thể, nên việc giữ invariant đầu vào giúp các case rõ ràng và tránh những trường hợp thiếu dữ liệu đáng lẽ phải xử lý riêng.

## 7. Một tiêu chí quan trọng: logic thuộc lớp nào?

### Trường hợp nên thiên về polymorphism

Giả sử các thao tác `pay()`, `reserve()` hoặc `fee()` là **hành vi mà mọi subtype đều phải cung cấp**, có quy tắc ổn định và được gọi nhiều nơi. Mẫu tốt là:

```java
static int totalFee(java.util.List<? extends Delivery> deliveries) {
    int total = 0;
    for (Delivery delivery : deliveries) {
        total += delivery.fee();
    }
    return total;
}
```

Đây là phương thức minh họa, giả định `Delivery` đã được định nghĩa. Người dùng chỉ gọi hợp đồng chung, không hỏi `delivery instanceof Courier` trước khi quyết định cách tính. Nếu thật sự muốn tính tổng lớn và an toàn với tràn số, có thể dùng `Math.addExact` hay kiểu số phù hợp; đó là quyết định domain riêng.

Nếu chỉ vì thích pattern mà chuyển logic `fee()` sang nhiều `switch` trong tầng service, các service trở nên biết quá nhiều về subtype. Hệ quả dễ thấy là sửa công thức phí phải tìm nhiều nơi.

### Trường hợp nên thiên về pattern matching

Các tác vụ **đọc cấu trúc** để chuyển đổi sang một dạng bên ngoài thường rất tự nhiên với `switch`:

- Hiển thị nhãn khác nhau cho các biến thể domain.
- Chuyển một kiểu event đóng thành DTO cho báo cáo hoặc giao thức bên ngoài.
- Phân loại một tập record hữu hạn để tạo thống kê.
- Thực hiện một phép biến đổi độc lập mới mà không cần thêm phương thức vào mọi record.

Khi `Delivery` chỉ gồm hai record thuộc quyền kiểm soát của domain, một `switch` có case rõ ràng có thể dễ hiểu hơn việc thêm `delivery.adminViewLabel()` vào giao diện chỉ vì một màn hình quản trị cần dữ liệu ấy.

**Ngoại lệ:** Nếu chức năng chuyển đổi chính là trách nhiệm lâu dài của đối tượng và được sử dụng nhiều nơi, việc đưa vào interface hay một service có tên vẫn đáng cân nhắc. Mục tiêu là đặt **một nguồn sự thật cho hành vi**, không nhất thiết là chọn một cú pháp duy nhất.

## 8. Khi nào nên phối hợp?

Trong dự án thực tế, lựa chọn thường không phải “100% pattern” hoặc “100% polymorphism”.

Một mô hình phối hợp tốt có thể là:

- **Domain:** interface có hợp đồng hành vi; subtype triển khai và xác thực invariant riêng.
- **Application service:** gọi hành vi qua interface, không biết nhiều về subtype nếu không cần.
- **Presentation/reporting:** dùng type/record patterns trong `switch` để tạo dữ liệu hiển thị hoặc định dạng cụ thể.
- **Boundary:** nhận dữ liệu từ ngoài, xác thực kiểu và cấu trúc trước khi chuyển thành đối tượng domain có hợp đồng ổn định.

Ví dụ ở phần 6 dùng `delivery.fee()` cho hành vi tính phí và `label(delivery)` cho mô tả. Đây là **sự kết hợp có trách nhiệm**, chứ không phải lặp lại hai con đường tính phí ở mọi nơi.

Một nguyên tắc dễ nhớ: **“Gọi phương thức khi muốn đối tượng hành động; khớp pattern khi muốn biết đối tượng thuộc trường hợp nào để thực hiện một phép chuyển đổi bên ngoài.”** Nguyên tắc này là gợi ý kiến trúc, không phải luật cứng. Một hệ thống có thể có các ràng buộc hiệu năng, tương thích, phân lớp hoặc kiểm thử khiến cách tổ chức khác phù hợp hơn.

## 9. Lỗi thường gặp khi lựa chọn

| Lỗi thiết kế | Tác hại | Hướng xử lý |
| --- | --- | --- |
| Kiểm tra kiểu chỉ để gọi phương thức có sẵn trên interface | Caller phụ thuộc các subtype vô ích. | Gọi phương thức qua interface để tận dụng dispatch đa hình. |
| Rải công thức nghiệp vụ giống nhau vào nhiều `switch` | Dễ lệch kết quả và bỏ sót nhánh khi sửa quy tắc. | Đặt một nguồn sự thật, thường là domain method hoặc service được định nghĩa rõ. |
| Thêm mọi tác vụ báo cáo/hiển thị vào interface domain | Interface phình ra, subtype phải phụ trách ngữ cảnh ngoài domain. | Dùng mapper/service riêng, có thể áp dụng pattern matching. |
| Dùng `switch` liệt kê subtype của interface mở mà không có fallback | Không thể xử lý implementation mới. | Sử dụng hành vi chung hoặc nhánh bao quát phù hợp. |
| Thêm `default` vô điều kiện vào mọi `switch` của sealed domain | Có thể che việc thiếu xử lý subtype mới. | Để compiler kiểm tra exhaustiveness khi cần cập nhật từng loại. |
| Đặt case tổng quát trước case cụ thể | Case sau bị dominated và có thể không biên dịch. | Đặt pattern cụ thể/guard trước nhánh rộng. |
| Nghĩ `sealed` tự kiểm tra invariant dữ liệu | Giá trị component vẫn có thể sai hoặc null nếu không kiểm tra. | Validation ở constructor/boundary; xử lý null theo hợp đồng. |
| Refactor từ đa hình sang pattern rồi đổi hành vi null/exception | Không còn tương đương, có thể phá API. | Chốt hợp đồng, viết test cho cả nhánh lỗi và dữ liệu biên. |
| Chọn chỉ dựa trên số dòng hay suy đoán hiệu năng | Bỏ qua chi phí bảo trì và vai trò domain. | Ưu tiên đúng trách nhiệm, rồi benchmark nếu hiệu năng quan trọng. |

## 10. Kịch bản refactor và kiểm thử

### Từ type check dư thừa sang polymorphism

Trước:

```java
static int fee(Delivery delivery) {
    if (delivery instanceof Courier courier) {
        return courier.fee();
    }
    if (delivery instanceof Pickup pickup) {
        return pickup.fee();
    }
    throw new IllegalArgumentException("Unsupported delivery");
}
```

Sau, khi `Delivery` đã có hợp đồng `fee()`:

```java
static int fee(Delivery delivery) {
    return delivery.fee();
}
```

Đây là mã minh họa cho lời gọi với đối tượng **khác null và thuộc hệ kiểu được định nghĩa**. Đường lỗi với null và loại không được hỗ trợ phải được đánh giá riêng trước khi tuyên bố refactor bảo toàn tuyệt đối hành vi.

### Từ nhiều visitor nhỏ sang một phép biến đổi dữ liệu

Nếu một nhiệm vụ chỉ cần chuyển tập record đóng thành mô tả bên ngoài, một `switch` trong một phương thức mapper có thể dễ đọc hơn việc tạo thêm phương thức vào mỗi subtype hoặc một visitor interface lớn. Nhưng nếu dự án đã có visitor mang nhiều ý nghĩa kiến trúc (ví dụ cần hỗ trợ double dispatch, xử lý trạng thái có cấu trúc hoặc các phiên bản Java cũ), không nên tự động xóa nó chỉ vì xuất hiện pattern matching.

### Bộ test nên có

- Với **mỗi subtype**, test hợp đồng polymorphic (`fee()`) và những phép chuyển đổi quan trọng (`label()`) trên giá trị bình thường.
- Với **giá trị biên**, test guard `when` (ví dụ `distanceKm = 10` so với `11`), invariant số âm, trường hợp rỗng và `null`.
- Với **thay đổi hierarchy**, biên dịch lại những `switch` cần exhaustiveness, tránh che khuất thiếu nhánh bằng `default` không cần thiết.
- Với **interface mở**, test bằng một implementation mới hoặc fake implementation để xác nhận caller không phụ thuộc vào danh sách type cụ thể.
- Với **refactor**, so sánh kết quả và kiểu exception khi yêu cầu bảo toàn hành vi. Không chỉ so sánh những kết quả thành công.

## 11. Tự kiểm tra

Giả sử ứng dụng có:

```java
sealed interface Message permits Email, Sms {
    String send();
}
record Email(String address) implements Message {
    public String send() { return "Sent email"; }
}
record Sms(String phone) implements Message {
    public String send() { return "Sent SMS"; }
}
```

**Bài 1:** Một service cần gửi thông điệp. Nên viết `if (m instanceof Email) ... else if (...)` hay `m.send()`?

**Đáp án:** Ưu tiên `m.send()` vì hành vi đã được định nghĩa trong hợp đồng `Message`. Việc gọi qua subtype sẽ lặp lại quyết định mà đa hình đã giải quyết.

**Bài 2:** Một màn hình cần hiển thị `"Email đến địa chỉ ..."` hoặc `"SMS đến số ..."`, nhưng domain không nên biết về wording của giao diện. Dùng gì?

**Đáp án:** Một mapper riêng với `switch` và record patterns, ví dụ:

```java
static String display(Message message) {
    return switch (message) {
        case Email(String address) -> "Email đến " + address;
        case Sms(String phone) -> "SMS đến " + phone;
        case null -> "Chưa chọn";
    };
}
```

Ví dụ minh họa này cần Java 21. Tập subtype `Email`, `Sms` được kiểm soát, nên có thể kiểm tra đầy đủ các case; `case null` biểu thị chính sách giao diện khi chưa có đối tượng.

**Bài 3:** Nếu phải cho đối tác bổ sung một loại `Message` mới ở module của họ, điều gì cần xem lại?

**Đáp án:** Đánh giá xem hợp đồng có nên chuyển thành **interface mở**, dùng một **nhánh `non-sealed`** hoặc tách extension point ra khỏi domain đóng. Những `switch` từng dựa vào tập subtype hữu hạn cũng phải được xem lại. Đây là quyết định kiến trúc chứ không chỉ sửa `permits`.

**Kết luận:** **Polymorphism** phù hợp khi muốn các subtype cùng thực hiện một hành vi thuộc hợp đồng; **pattern matching** phù hợp khi một thao tác cần phân loại và đọc dữ liệu của một tập biến thể, nhất là record trong sealed hierarchy. Để code dễ đọc và bền vững, hãy xét **trách nhiệm của logic**, **chiều thay đổi dự kiến**, **quy tắc null**, **khả năng exhaustiveness** và **số nơi phải sửa khi domain phát triển**. Hai kỹ thuật thường bổ sung cho nhau tốt hơn là thay thế hoàn toàn cho nhau.
