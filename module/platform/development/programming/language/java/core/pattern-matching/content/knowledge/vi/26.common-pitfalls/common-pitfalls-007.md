# Lồng record pattern quá sâu: dấu hiệu lỗi và cách refactor trong Java 21

## 1. Vấn đề thực tế

Record pattern giúp Java kiểm tra kiểu và **deconstruct** dữ liệu ngay trong `instanceof` hoặc nhãn `case`. Với domain model có các record lồng nhau, ta có thể đọc thẳng giá trị ở tầng sâu:

```java
record Point(int x, int y) {}
record Address(String city, Point location) {}
record Buyer(String name, int level) {}
record Purchase(String id, Buyer buyer, Address destination, long total) {}
```

Một pattern như sau là hợp lệ:

```java
case Purchase(
        var id,
        Buyer(var name, var level),
        Address(var city, Point(var x, var y)),
        var total) when level >= 2 && total >= 1_000L ->
    "Đơn ưu tiên: " + id;
```

Nó biểu diễn cây `Purchase → Buyer` và `Purchase → Address → Point`, đồng thời trích xuất bảy biến. Khi đây đúng là cấu trúc cần biểu đạt, cú pháp khá ngắn gọn. Nhưng nếu thêm hàng loạt điều kiện, các nhánh dự phòng, kiểm tra null và truy cập hệ thống khác, **lồng record pattern quá sâu trở thành lỗi về khả năng đọc và bảo trì**.

Người đọc có thể gặp khó khăn khi phải trả lời cùng lúc:

- Đối tượng phải khớp những tầng record nào mới vào được nhánh?
- Một component null khiến pattern không khớp ở tầng nào?
- Guard `when` được đánh giá hay chưa?
- Biến nào có kiểu gì, nằm trong scope nào và được dùng ở đâu?
- Nếu một tầng con không khớp, nhánh nào sẽ xử lý dữ liệu đó?
- Sửa quy tắc nghiệp vụ có buộc chỉnh lại nhiều pattern giống nhau không?

**Không có quy tắc của Java cấm pattern lồng ba, bốn hay nhiều tầng.** “Quá sâu” là đánh giá thiết kế dựa trên mức độ rõ ràng, độ bền khi model thay đổi, khả năng kiểm thử và sự liên quan của mỗi tầng với mục đích nhánh.

Bài viết tập trung vào **lỗi thường gặp**, cách nhận diện, hậu quả cụ thể và phương pháp đơn giản hóa mà vẫn giữ nguyên hành vi.

**Phiên bản:** Record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) đều là tính năng chính thức từ **Java 21**. Ví dụ chạy được trong bài sử dụng JDK 21+ và không cần `--enable-preview`. `record` đã là tính năng chuẩn từ Java 16, nhưng cú pháp record pattern như `Point(var x, var y)` không có trong Java 17 chuẩn.

## 2. Đọc đúng một nested record pattern từ ngoài vào trong

Xét pattern:

```java
Purchase(
    var id,
    Buyer(var name, var level),
    Address(var city, Point(var x, var y)),
    var total
)
```

Cấu trúc khớp tương ứng:

```text
Purchase                          ← tầng ngoài cùng
├── id: String                    ← var id
├── buyer: Buyer                  ← Buyer(...)
│   ├── name: String              ← var name
│   └── level: int                ← var level
├── destination: Address          ← Address(...)
│   ├── city: String              ← var city
│   └── location: Point           ← Point(...)
│       ├── x: int                ← var x
│       └── y: int                ← var y
└── total: long                   ← var total
```

Cách suy luận:

1. Giá trị selector phải là `Purchase` không-null.
2. `Buyer(...)` yêu cầu component `buyer` khớp một đối tượng `Buyer` không-null.
3. `Address(...)` yêu cầu `destination` là `Address` không-null.
4. `Point(...)` yêu cầu `destination.location` là `Point` không-null.
5. Các `var` lần lượt ràng buộc component vào biến với **kiểu suy luận từ khai báo record**.
6. Chỉ sau khi **toàn bộ pattern** khớp, guard `when` của nhánh mới được đánh giá.

Đây là **kiểm tra cấu trúc**, không tự xác thực tên buyer, tên thành phố hoặc số tiền theo chính sách nghiệp vụ. Ví dụ `var name` nhận giá trị `String` của component và **có thể nhận null**. Ngược lại `Buyer(...)` là một record pattern, nên không khớp nếu component tương ứng null.

Thấy nhiều dấu ngoặc không có nghĩa compiler chạy chậm một cách chắc chắn. Rủi ro thường đáng quan tâm trước tiên là **độ phức tạp nhận thức** và **nhánh xử lý dễ bị bỏ sót**. Đánh giá hiệu năng phải dựa trên phép đo với workload thực tế.

## 3. Sáu dấu hiệu pattern đã lồng quá sâu

| Dấu hiệu | Điều người đọc phải làm | Hậu quả có thể xảy ra |
| --- | --- | --- |
| Nhiều tầng nhưng chỉ dùng một giá trị cuối | Đi theo toàn bộ cây record để tìm một cờ | Code gắn chặt vào cấu trúc không liên quan |
| Nhiều biến `var` không dùng | Nhớ tên và vị trí component dư thừa | Khó review; sai thứ tự component dễ bị bỏ qua |
| Guard dài với nhiều quy tắc khác loại | Vừa giải cây record, vừa giải Boolean | Khó thấy điều kiện quan trọng và điểm null-safety |
| Các nhánh lặp lại một nested pattern | So sánh nhiều cây gần giống nhau | Khi thay đổi model dễ sửa thiếu một nhánh |
| Fallback phụ thuộc tầng null khó đoán | Phân biệt pattern fail và guard false | Dữ liệu hợp lệ theo nghĩa khác có thể vào nhánh bất ngờ |
| Domain model thay đổi nhỏ kéo theo nhiều sửa đổi pattern | Cập nhật lại nhiều `case` với số component mới | Tăng chi phí bảo trì và test regression |

Các dấu hiệu này **không phải lỗi compile tất yếu**. Một nested pattern ngắn có thể tốt hơn nhiều lời gọi accessor, nhưng khi điều kiện và cấu trúc đã che khuất *ý định của nhánh*, cần cân nhắc refactor.

### Ví dụ: chỉ cần buyer VIP nhưng kiểm tra cả địa chỉ

```java
// Giả sử Purchase, Buyer, Address, Point đã được khai báo.
case Purchase(
        var id,
        Buyer(var name, var level),
        Address(var city, Point(var x, var y)),
        var total) when level >= 2 ->
    "Khách hạng cao";
```

Nếu mục tiêu **chỉ** là kiểm tra `level >= 2`, pattern trên phụ thuộc không cần thiết vào `destination` và `location`. Một `Purchase` có buyer hạng cao nhưng địa chỉ đang thiếu `Point` **không khớp**, dù logic nhận diện hạng buyer không cần biết tọa độ.

Một lựa chọn sát ý định hơn:

```java
case Purchase(var id, Buyer(var name, var level),
              var destination, var total)
        when level >= 2 ->
    "Khách hạng cao";
```

Hoặc nếu muốn điều phối ở cấp entity:

```java
case Purchase p when isHighTierBuyer(p.buyer()) ->
    "Khách hạng cao";
```

Hai đoạn cuối cần đặt trong `switch` có helper/thành phần phù hợp; chúng là **mẫu minh họa**, không phải chương trình độc lập. Điều quan trọng: khi không cần dữ liệu địa chỉ, đừng tạo thêm điều kiện khớp địa chỉ mà bài toán không yêu cầu.

## 4. Phân biệt “pattern không khớp” và “guard sai”

Đây là nguồn lỗi thường gặp nhất ở nested record pattern.

Ví dụ:

```java
case Purchase(
        var id,
        Buyer(var name, var level),
        Address(var city, Point(var x, var y)),
        var total)
        when level >= 2 && total >= 1_000L ->
    "Ưu tiên";
```

Bốn input có thể dẫn tới những kết quả khác nhau:

| Dữ liệu | Pattern có khớp không? | Guard có được xét không? |
| --- | --- | --- |
| `buyer == null` | Không, dừng ở `Buyer(...)` | Không |
| `destination == null` | Không, dừng ở `Address(...)` | Không |
| `destination.location() == null` | Không, dừng ở `Point(...)` | Không |
| `buyer.level() == 1`, toàn bộ record con có mặt | Có | Có, nhưng trả false |
| `buyer.level() == 2`, `total >= 1000`, record con đầy đủ | Có | Có, trả true |

**Về ý nghĩa:** null trong một **record pattern lồng** khiến toàn bộ pattern không khớp; null trong component được bắt bằng `var` vẫn có thể là một giá trị đã ràng buộc. Guard `when` không được chạy khi pattern thất bại trước đó.

Cách đọc rõ nhánh fallback là quan trọng vì người viết dễ tưởng một guard null check có thể “cứu” pattern con:

```java
// CỐ Ý SAI VỀ Ý ĐỊNH: khi location null,
// Point(var x, var y) đã không khớp,
// nên guard phía sau không thể chạy để xử lý null.
case Purchase(var id, var buyer,
              Address(var city, Point(var x, var y)),
              var total)
        when city == null ->
    "Thành phố thiếu";
```

Guard `city == null` có thể hoạt động khi Address/Point tồn tại và city null. **Nó không xử lý trường hợp Point null**, dù tác giả có thể tưởng như vậy.

Muốn xét thiếu Point, dừng ở mức nông hơn:

```java
case Purchase(var id, var buyer,
              Address(var city, var location),
              var total)
        when location == null ->
    "Thiếu tọa độ";
```

Bằng cách này, `var location` có thể giữ null; sau khi pattern Address thành công, guard mới quyết định thiếu tọa độ. Lưu ý: nếu `destination == null`, chính `Address(...)` vẫn không khớp. Muốn xử lý cả destination null, cần bắt component bằng `var destination` ở tầng Purchase.

## 5. Guard quá dài làm che mất lý do chọn case

Một nested pattern sâu cộng với guard dài thường trộn hai loại kiểm tra khác nhau:

- **Kiểm tra cấu trúc**: có đúng các record con cần thiết hay không.
- **Chính sách nghiệp vụ**: tên hợp lệ, hạng khách, khu vực được phép, giá trị đơn, ngưỡng rủi ro...

Ví dụ:

```java
case Purchase(
        var id,
        Buyer(var name, var level),
        Address(var city, Point(var x, var y)),
        var total)
        when id != null && !id.isBlank()
            && name != null && !name.isBlank()
            && level >= 2
            && city != null && !city.isBlank()
            && x >= 0 && y >= 0
            && total >= 1_000L ->
    "Ưu tiên: " + id;
```

Code này có thể đúng, nhưng người đọc phải lần theo **cấu trúc nhiều tầng + bảy biến + nhiều điều kiện**. Khi nghiệp vụ mở rộng, rất dễ thêm một kiểm tra ở sai nhánh hoặc làm guard có side effect khó thấy.

Một cách đơn giản hóa là đặt tên cho chính sách:

```java
case Purchase purchase when isPriority(purchase) ->
    "Ưu tiên: " + purchase.id();
```

`isPriority` có thể được chia thành các kiểm tra con dễ hiểu: buyer, destination, tổng tiền, ID. Phần `switch` lúc này trả lời câu hỏi ở cấp nghiệp vụ, còn helper chịu trách nhiệm chi tiết.

**Không đặt helper theo kiểu `check1`, `validateStuff` hoặc `doThing`**: tên mơ hồ chỉ chuyển độ khó từ một biểu thức dài sang nhiều file. Một helper tốt nên có hợp đồng rõ (input, kết quả, xử lý null) và dễ test.

## 6. Chương trình Java 21 hoàn chỉnh: phiên bản sâu và phiên bản dễ đọc

Ví dụ này dùng cùng một domain model nhưng hai cách phân loại:

- `classifyDeep` lồng các record pattern vào một nhánh `switch`.
- `classifyReadable` giữ phần điều phối ở mức `Purchase`, gọi `isPriority` để kiểm tra cấu trúc và điều kiện bằng hai nhóm nhỏ hơn.
- Hàm `verify` so sánh **cả hai phiên bản** và kiểm tra kết quả mong đợi. Mục tiêu là thấy một refactor có thể giữ hành vi với các đầu vào tiêu biểu.

Tạo tệp **`DeepRecordPatternDemo.java`**:

```java
public class DeepRecordPatternDemo {

    record Point(int x, int y) {}

    record Address(String city, Point location) {}

    record Buyer(String name, int level) {}

    record Purchase(String id, Buyer buyer,
                    Address destination, long total) {}

    static boolean nonBlank(String text) {
        return text != null && !text.isBlank();
    }

    // Bản 1: một pattern sâu và một guard dài.
    static String classifyDeep(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case Purchase(
                    var id,
                    Buyer(var name, var level),
                    Address(var city, Point(var x, var y)),
                    var total)
                    when nonBlank(id)
                        && nonBlank(name)
                        && level >= 2
                        && nonBlank(city)
                        && x >= 0 && y >= 0
                        && total >= 1_000L ->
                "Ưu tiên: " + id;

            case Purchase(var id, var buyer,
                          var destination, var total)
                    when buyer == null || destination == null ->
                "Thiếu dữ liệu: " + id;

            case Purchase(var id, var buyer,
                          var destination, var total) ->
                "Thông thường: " + id;

            default -> "Không phải Purchase";
        };
    }

    // Kiểm tra điều kiện theo nhóm, có thể unit-test độc lập.
    static boolean isPriority(Purchase purchase) {
        if (!(purchase.buyer() instanceof Buyer(var name, var level))) {
            return false;
        }

        if (!(purchase.destination() instanceof
                Address(var city, Point(var x, var y)))) {
            return false;
        }

        return nonBlank(purchase.id())
            && nonBlank(name)
            && level >= 2
            && nonBlank(city)
            && x >= 0 && y >= 0
            && purchase.total() >= 1_000L;
    }

    // Bản 2: mỗi case thể hiện một tình huống rõ ý nghĩa.
    static String classifyReadable(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case Purchase purchase when isPriority(purchase) ->
                "Ưu tiên: " + purchase.id();

            case Purchase purchase when
                    purchase.buyer() == null
                    || purchase.destination() == null ->
                "Thiếu dữ liệu: " + purchase.id();

            case Purchase purchase ->
                "Thông thường: " + purchase.id();

            default -> "Không phải Purchase";
        };
    }

    static void verify(Object value, String expected) {
        String deep = classifyDeep(value);
        String readable = classifyReadable(value);

        if (!deep.equals(readable) || !deep.equals(expected)) {
            throw new AssertionError(
                "Không khớp: " + deep + " / " + readable);
        }
        System.out.println(readable);
    }

    public static void main(String[] args) {
        verify(new Purchase(
            "P-1",
            new Buyer("An", 2),
            new Address("Huế", new Point(1, 2)),
            1_200L), "Ưu tiên: P-1");

        verify(new Purchase(
            "P-2",
            new Buyer("Bình", 1),
            new Address("Huế", new Point(1, 2)),
            1_200L), "Thông thường: P-2");

        verify(new Purchase(
            "P-3",
            null,
            new Address("Huế", new Point(1, 2)),
            1_200L), "Thiếu dữ liệu: P-3");

        verify(new Purchase(
            "P-4",
            new Buyer("Chi", 2),
            new Address("Huế", null),
            1_200L), "Thông thường: P-4");

        verify(new Purchase(
            "P-5",
            new Buyer(null, 2),
            new Address("Huế", new Point(1, 2)),
            1_200L), "Thông thường: P-5");

        verify(new Purchase(
            "P-6",
            new Buyer("Dũng", 2),
            new Address("", new Point(1, 2)),
            1_200L), "Thông thường: P-6");

        verify(new Purchase(
            "P-7",
            new Buyer("Em", 2),
            new Address("Huế", new Point(1, 2)),
            999L), "Thông thường: P-7");

        verify("abc", "Không phải Purchase");
        verify(null, "Không có dữ liệu");
    }
}
```

Biên dịch và chạy từ thư mục có tệp bằng **JDK 21 hoặc mới hơn**:

```bash
javac --release 21 -encoding UTF-8 DeepRecordPatternDemo.java
java DeepRecordPatternDemo
```

Kết quả dự kiến:

```text
Ưu tiên: P-1
Thông thường: P-2
Thiếu dữ liệu: P-3
Thông thường: P-4
Thông thường: P-5
Thông thường: P-6
Thông thường: P-7
Không phải Purchase
Không có dữ liệu
```

### 6.1. Truy vết kết quả từng trường hợp

| Đầu vào | Bản sâu diễn ra thế nào? | Vì sao hai bản có cùng kết quả? |
| --- | --- | --- |
| P-1: buyer hạng 2, city có nội dung, Point (1,2), total 1200 | Tất cả record con khớp; guard đúng | `isPriority` cũng trả true |
| P-2: buyer hạng 1 | Pattern khớp; guard `level >= 2` sai | Helper trả false, vào nhánh thông thường |
| P-3: `buyer == null` | `Buyer(...)` không khớp; nhánh thứ hai bắt null | Helper trả false; nhánh thiếu dữ liệu cũng bắt null |
| P-4: `Address.location == null` | `Point(...)` không khớp; nhánh thiếu dữ liệu không bắt vì Address vẫn tồn tại | Helper trả false; vào nhánh thông thường |
| P-5: `Buyer.name == null` | Pattern khớp; `nonBlank(name)` sai | Helper cũng dùng `nonBlank(name)` |
| P-6: `Address.city == ""` | Pattern khớp; `nonBlank(city)` sai | Helper cũng kiểm tra city |
| P-7: total 999 | Pattern khớp; guard ngưỡng 1000 sai | Helper cũng kiểm tra total |
| `"abc"` | Không phải `Purchase` | Cả hai vào default |
| `null` | `case null` | Cả hai xử lý null tường minh |

**Điểm đặc biệt ở P-4:** đối tượng `Address` có mặt nhưng `Point` thiếu. Theo các nhánh đã viết, nó được xem là **thông thường**, không phải “thiếu dữ liệu”, vì nhánh thiếu dữ liệu chỉ kiểm tra buyer/destination ở cấp Purchase. Đây là **quy tắc demo để giữ hành vi tương đương**, không phải gợi ý rằng thiếu tọa độ luôn được chấp nhận trong domain thật.

Nếu ứng dụng yêu cầu phân loại thiếu tọa độ thành lỗi, hãy **thay đổi chính sách có chủ đích**, thêm test và cập nhật cả hai phiên bản tương ứng. Đừng đổi ngầm hành vi trong một refactor chỉ nhằm tăng readability.

### 6.2. Tại sao version tách helper dễ review?

Phần `switch` thứ hai bộc lộ ba tình huống ở cùng cấp:

1. Purchase thỏa chính sách ưu tiên.
2. Purchase thiếu Buyer hoặc Address.
3. Purchase còn lại.

Helper `isPriority` vẫn cần kiểm tra các record con, nhưng tách chúng ra theo từng nhóm và trả `false` sớm nếu nhóm cần thiết không có. Reviewer có thể kiểm tra riêng logic này mà không phải lần theo nhiều nhánh `case`.

**Đừng khẳng định mọi refactor đều tương đương một cách tự động.** Ví dụ trên dùng record có **accessor mặc định và không có side effect**. Một record có accessor tùy biến, ném exception hoặc thay đổi kết quả giữa các lần gọi có thể làm cách deconstruct và cách gọi accessor trực tiếp khác nhau. Đổi vị trí/lần truy cập trong code như vậy cần kiểm tra hành vi cụ thể.

## 7. Những giải pháp thay thế để giảm độ sâu

### A. Dùng type pattern rồi helper

Thay vì mở toàn bộ cây ngay trong `case`:

```java
case Purchase purchase when isPriority(purchase) ->
    "Ưu tiên: " + purchase.id();
```

Tốt khi quy tắc nghiệp vụ dài, lặp lại hoặc cần test. Không bắt buộc helper phải ở file khác; một phương thức `private static` có tên rõ nghĩa trong cùng class thường đủ.

### B. Chỉ deconstruct tới tầng thật sự cần

Nếu cần xử lý toàn bộ `destination`, dùng:

```java
case Purchase(var id, var buyer, var destination, var total) ->
    describeDestination(destination);
```

`var destination` suy luận kiểu `Address` từ component. Nó **có thể là null**, nên `describeDestination` phải có hợp đồng về null hoặc caller phải kiểm tra. Cách này tránh yêu cầu `Point` tồn tại khi hành động chỉ cần metadata của Address.

### C. Dùng nested pattern có mức sâu vừa đủ

Nếu một quy tắc thật sự liên quan đến `Buyer` nhưng không liên quan `Address.Point`:

```java
case Purchase(var id, Buyer(var name, var level),
              var destination, var total)
        when level >= 2 ->
    "Buyer hạng cao: " + id;
```

Đây là ví dụ inline vẫn rõ ràng. **Không nên bỏ record patterns bằng mọi giá**: độ sâu phù hợp là độ sâu mà người đọc cần để thấy điều kiện quan trọng ngay tại điểm phân nhánh.

### D. Đặt invariant ở constructor khi hợp lý

Nếu mọi `Purchase` bắt buộc có buyer, destination, location và các trường có giá trị hợp lệ, constructor có thể chặn dữ liệu sai sớm. Ví dụ nhỏ:

```java
record Address(String city, Point location) {
    Address {
        java.util.Objects.requireNonNull(location, "location");
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("city required");
        }
    }
}
```

Đây là **mẫu khai báo minh họa**, không thay thế record Address của chương trình chính. Khi constructor bảo vệ invariant, các nơi tiêu thụ dữ liệu có ít nhánh null hơn.

Tuy nhiên, **không thay đổi hợp đồng domain chỉ để giảm số case**. Một domain cho phép địa chỉ thiếu tạm thời hoặc cho phép nhập liệu dở dang không thể đơn giản cấm null mà không cân nhắc luồng tạo/sửa dữ liệu.

### E. Đặt tên cho điều kiện thay vì tăng số tầng

Thay `when` gồm mười điều kiện bằng `when isPriority(purchase)` chỉ đáng làm nếu tên diễn đạt đúng chính sách. Có thể chia tiếp thành `hasEligibleBuyer`, `hasServiceableAddress` hoặc `meetsMinimumAmount`, nhưng không cần tạo hàng loạt helper một dòng vô nghĩa.

## 8. Guard, null và flow scoping: ba điểm phải giữ khi refactor

### 8.1. Scope của biến pattern

`x` và `y` trong `Point(var x, var y)` chỉ được dùng ở nơi compiler biết pattern khớp, như guard `when` và thân `case` đó. Chúng không tự trở thành biến của `case` tiếp theo.

Trong `if`, phép `&&` có short-circuit:

```java
if (value instanceof Purchase(var id, var buyer,
                              var destination, var total)
        && buyer != null && destination != null) {
    System.out.println(id);
}
```

Pattern ràng buộc `buyer` và `destination`, sau đó điều kiện kiểm tra null. Không dùng chúng ở vế phải của `||` sau `instanceof` khi pattern có thể chưa khớp.

### 8.2. Null ở record con khác null ở component `var`

`Buyer(var name, var level)` không khớp khi buyer null. Nhưng `var name` có thể ràng buộc một `String` null nếu record Buyer tồn tại và component name null.

Do đó:

```java
case Purchase(var id, var buyer, var destination, var total)
        when buyer == null || destination == null ->
    "Thiếu dữ liệu";
```

có thể xử lý Buyer hoặc Address null. Trong khi:

```java
case Purchase(var id,
              Buyer(var name, var level),
              Address(var city, Point(var x, var y)),
              var total) when name == null ->
    "Thiếu tên buyer";
```

không thể chạy nếu `buyer`, `destination` hoặc `location` null, vì các nested record pattern đó đã thất bại trước.

### 8.3. Dominance và nhánh dự phòng

Với cùng một kiểu Purchase, đặt case đặc thù có guard trước case không guard:

```java
// Đúng thứ tự:
case Purchase p when isPriority(p) -> "Ưu tiên";
case Purchase p -> "Thông thường";
```

Ví dụ **cố ý sai, không biên dịch**:

```java
case Purchase p -> "Thông thường";
case Purchase p when isPriority(p) -> "Ưu tiên"; // Dominated
```

`case Purchase p` đầu tiên đã bắt mọi Purchase không-null, nên nhánh sau không thể được chọn. Việc giảm độ sâu không được làm mất thứ tự ưu tiên của các điều kiện hay tính bao phủ của `switch expression`.

## 9. Khi nào nested record pattern là lựa chọn tốt?

Một nested pattern được đánh giá là **hữu ích** khi nó biểu diễn trực tiếp đặc điểm cấu trúc cần phân loại, dùng ít biến, guard ngắn và không che khuất chính sách.

Ví dụ kiểm tra một hình chữ nhật có hai điểm đầu/cuối:

```java
record Rectangle(Point first, Point second) {}

// Nhãn case minh họa trong switch:
case Rectangle(Point(var x1, var y1), Point(var x2, var y2))
        when x1 <= x2 && y1 <= y2 ->
    "Hai điểm theo đúng thứ tự";
```

Ở đây việc cả hai component là `Point` không-null là **một phần thiết yếu của điều kiện**, và các biến lá đều được sử dụng. Pattern lồng hai tầng bộc lộ quan hệ dữ liệu rõ hơn so với một chuỗi accessor dài.

Ngược lại, nếu điều kiện chỉ cần `rectangle.first() != null`, việc tách cả `x1/y1/x2/y2` là dư thừa và có thể làm mất những trường hợp đáng lẽ phải xử lý.

**Nguyên tắc:** không đếm ngoặc một cách cơ học. Hãy so sánh **độ sâu cần thiết cho nghiệp vụ** với **độ sâu thực tế của cú pháp**.

## 10. Rủi ro khi đổi domain model và khi dùng accessor tùy biến

Record pattern có phụ thuộc vào **số thứ tự component** và **kiểu đã khai báo**. Thay đổi component trong record public API có thể tác động tới constructor, accessor và tất cả pattern `Record(...)` có số lượng component tương ứng. Nếu cùng một nested pattern được nhân bản ở nhiều nhánh, khối lượng thay đổi tăng.

Đặt ranh giới tách dữ liệu qua helper hoặc phương thức domain giúp giảm số điểm phải sửa khi các record thay đổi. Tuy nhiên, helper cũng cần được thiết kế theo hợp đồng rõ ràng; chỉ đẩy một cây lồng vào hàm vô danh không giải quyết được coupling.

Ngoài ra, record có thể khai báo accessor tùy biến. Khi deconstruction, việc gọi accessor không nhất thiết không có tác dụng phụ; một accessor có thể ném exception. **Không giả định đổi từ record pattern sang một chuỗi accessor sẽ luôn giữ nguyên thứ tự và số lần gọi**. Nếu hệ thống có accessor bất thường, cần kiểm thử kết quả/exception/side effect. Với value object, accessor đơn giản và ổn định thường là thiết kế dễ hiểu hơn.

## 11. Quy trình refactor an toàn

1. **Ghi mục đích mỗi case.** Ví dụ “đơn nào được ưu tiên?” thay vì “tách được các component nào?”.
2. **Vẽ hoặc đọc cây record.** Đánh dấu tầng thực sự cần cho câu hỏi nghiệp vụ.
3. **Kiểm kê biến được dùng.** Không deconstruct những component không đóng vai trò trong điều kiện hoặc kết quả.
4. **Chia cấu trúc và chính sách.** Record pattern kiểm tra hình dạng; `when`/helper kiểm tra dữ liệu.
5. **Đặt tên helper có ý nghĩa.** Một tên như `isPriority` làm rõ policy hơn chuỗi Boolean dài.
6. **Xác định nhánh null.** Thử null ở Buyer, Address, Point và các field chuỗi; phân biệt pattern fail với guard false.
7. **Kiểm tra thứ tự case.** Guard case đứng trước case rộng hơn; không tạo dominance.
8. **So sánh before/after.** Test mỗi đường đi quan trọng, kể cả output, exception và side effect nếu có.
9. **Đọc lại toàn bộ switch.** Người mới có thể nêu lý do chọn nhánh mà không phải lần qua năm record và nhiều cặp ngoặc không?
10. **Chỉ tối ưu hiệu năng khi có dữ liệu.** Độ ngắn của pattern hoặc số helper không tự chứng minh tốc độ tốt hơn.

Với hệ thống nghiệp vụ thực tế, bộ test nên có cả input hợp lệ, field rỗng, tầng record null, nhánh dự phòng, type khác, selector null và giới hạn số tiền/ngưỡng.

## 12. Những lỗi thường gặp khi “sửa” pattern quá sâu

| Cách sửa sai | Vấn đề | Cách xử lý tốt hơn |
| --- | --- | --- |
| Xóa `Point(...)` khỏi pattern mà không kiểm tra logic | Nhánh có thể bắt thêm input với Point null | Quyết định chính sách Point null và test hành vi |
| Đưa mọi điều kiện vào một helper tên `check` | Chỉ giấu độ phức tạp, không rõ ý định | Đặt tên theo domain, chia nhóm điều kiện |
| Xem `var address` như địa chỉ chắc chắn không-null | `var` có thể nhận component null | Thêm null guard hoặc constructor invariant |
| Tưởng guard null chạy trước nested record pattern | Pattern đã fail thì guard không được xét | Bắt component nông hơn để xử lý null |
| Đặt case tổng quát trước case có guard | Case sau bị dominated | Sắp xếp case cụ thể trước |
| Dùng record pattern để validate toàn bộ domain | Matching không thay thế invariant/validation | Constructor hoặc application validation có trách nhiệm riêng |
| Tách helper rồi thay thứ tự gọi accessor tùy biến | Có thể đổi exception/side effects | Kiểm tra hợp đồng record và test |
| Chỉ test trường hợp ưu tiên thành công | Bỏ sót null, guard false và fallback | Viết bảng tình huống như mục 6 |
| Cho rằng nhiều tầng luôn làm chậm runtime | Không có bằng chứng từ code đơn thuần | Đo benchmark phù hợp nếu có nghi ngờ thực tế |
| Tránh nested pattern tuyệt đối | Mất sự trực tiếp khi cấu trúc chính là nghiệp vụ | Giữ pattern vừa đủ, gọn, dễ đọc |

## 13. Bài tập và đáp án gợi ý

**Bài 1 — Đếm điều kiện cấu trúc.** Với `Purchase(var id, Buyer(var name, var level), Address(var city, Point(var x, var y)), var total)`, những thành phần record nào phải khác null để pattern khớp? Đáp án: **Purchase, Buyer, Address và Point** đều phải là record tương ứng không-null. `id`, `name` và `city` có thể null nếu chỉ được bắt bằng `var`.

**Bài 2 — Giảm độ sâu.** Quy tắc chỉ cần buyer hạng từ 2 trở lên. Hãy viết lại pattern không phụ thuộc destination/Point. Gợi ý: `Purchase(var id, Buyer(var name, var level), var destination, var total) when level >= 2`.

**Bài 3 — Phân biệt null.** Với Purchase có Buyer hợp lệ, Address hợp lệ nhưng `Address.location == null`, nhánh ưu tiên trong `classifyDeep` có được xét guard không? Đáp án: **không**; nested `Point(...)` không khớp.

**Bài 4 — Kiểm tra tính tương đương.** Chạy `DeepRecordPatternDemo.java`. Thêm input có `destination == null`, `id == null`, `Point(-1, 2)` và total đúng bằng 1000. Dự đoán cùng một kết quả từ hai cách phân loại.

**Bài 5 — Sửa policy có chủ đích.** Nghiệp vụ mới yêu cầu “location null phải báo thiếu dữ liệu”. Chỉ ra vì sao hai phiên bản gốc **không** làm vậy với P-4. Hãy cập nhật helper/nhánh fallback và kiểm tra P-4 được phân loại mới, không coi đó là refactor không thay đổi hành vi.

**Bài 6 — Đặt tên chính sách.** Nếu có thêm kiểm tra khu vực phục vụ, mức rủi ro và trạng thái tài khoản, bạn sẽ giữ tất cả trong `when` hay tách `isPriorityPurchase`? Giải thích dựa trên số quy tắc, test và khả năng thay đổi.

**Bài 7 — Review.** Tìm một `switch` pattern matching trong dự án và ghi lại: mức sâu, số biến thực sự dùng, guard, fallback, null từng tầng, nhánh bị dominance (nếu có), và hai test cần bổ sung. Không thay đổi code trước khi xác định hợp đồng hành vi.

## 14. Tổng kết

**Lồng record pattern quá sâu** không phải lỗi cú pháp mà là lỗi thiết kế xuất hiện khi cây pattern dài hơn nhu cầu của nhánh, làm ẩn điều kiện khớp, tăng coupling và khó quản lý null/guard/fallback.

Hướng xử lý:

- Chỉ deconstruct những tầng **thực sự cần** để quyết định.
- Phân biệt **record pattern lồng yêu cầu khớp kiểu không-null** với **`var` nhận component có thể null**.
- Đặt chính sách phức tạp trong helper có tên rõ ràng; giữ `switch` ở đúng mức điều phối/phân loại.
- Bảo toàn xử lý null, thứ tự case, dominance và exception khi refactor.
- Dùng test so sánh trước/sau, không suy đoán rằng biểu thức ngắn hơn chắc chắn tương đương.

### Tài liệu tham khảo

- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
