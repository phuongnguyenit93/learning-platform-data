# Lập chỉ mục và phát hiện bản ghi trùng theo khóa nghiệp vụ

## 1. Bài toán: từ danh sách bản ghi đến chỉ mục tra cứu đáng tin cậy

Trong chương **Mẫu xử lý dữ liệu thực tế** của **JAVA_STREAM_API**, các pipeline `filter`, `map`, `collect` và `reduce` không chỉ dùng để biến đổi danh sách. Một ứng dụng thường nhận nhiều bản ghi từ API, file hoặc hệ thống đối tác, rồi cần trả lời nhanh:

- Có bản ghi nào mang cùng **khóa nghiệp vụ** hay không?
- Với mỗi khóa, cần chọn **một bản ghi đại diện**, gộp giá trị hay **từ chối cả nhóm**?
- Có thể tạo `Map<Key, Record>` để tra cứu trực tiếp thay vì quét lại `List` nhiều lần không?
- Cách chuẩn hóa khóa có làm hai bản ghi vốn khác nhau bị coi là trùng hay không?
- Làm sao báo cáo bản ghi bị trùng để kiểm tra dữ liệu nguồn, thay vì âm thầm ghi đè?

Ví dụ hệ thống nhận các bản ghi tồn kho:

~~~text
Nguồn:
[tenant=T1, sku=" book ", version=1, quantity=10]
[tenant=T1, sku="BOOK",   version=2, quantity=8]
[tenant=T1, sku="PEN",    version=1, quantity=5]
[tenant=T2, sku="BOOK",   version=1, quantity=100]

Quy tắc nghiệp vụ:
- SKU không phân biệt chữ hoa/thường và khoảng trắng đầu/cuối.
- Một SKU chỉ duy nhất trong phạm vi một tenant.
- Các bản ghi có cùng tenant + SKU chuẩn hóa là cùng khóa.
- version càng lớn càng mới; quantity là snapshot, KHÔNG phải lượng để cộng.

Khóa chuẩn hóa:
(T1, BOOK) -> 2 bản ghi  -> cần kiểm tra trùng -> chọn version 2
(T1, PEN)  -> 1 bản ghi  -> hợp lệ
(T2, BOOK) -> 1 bản ghi  -> độc lập với (T1, BOOK)
~~~

Một kết quả thường gồm **hai sản phẩm riêng**:

1. **Chỉ mục cuối cùng** `Map<BusinessKey, Record>` để truy vấn nhanh theo khóa.
2. **Báo cáo chất lượng dữ liệu** chứa những khóa trùng và các bản ghi liên quan.

Nếu chỉ tạo Map rồi bỏ qua thông tin trùng, ta có thể đánh mất dấu vết một lỗi nghiệp vụ nghiêm trọng.

Bài dùng **Java 17+** với `record`, `Stream.toList()` và `Collectors`. Mục đích là thiết kế quy trình có hợp đồng rõ ràng, nhận biết các giới hạn về `null`, thứ tự, dữ liệu mutable và xử lý song song. Đây là một mẫu xử lý dữ liệu trong bộ môn Stream API, không phải cơ chế thay thế ràng buộc duy nhất ở cơ sở dữ liệu.

## 2. Khóa nghiệp vụ không nhất thiết là ID của bản ghi

**Khóa kỹ thuật** thường do hệ thống tạo ra, ví dụ ID bản ghi, UUID hoặc số thứ tự import. **Khóa nghiệp vụ** là tập thuộc tính xác định một thực thể theo quy tắc domain.

| Bối cảnh | Khóa kỹ thuật | Khóa nghiệp vụ có thể là |
| --- | --- | --- |
| Sản phẩm theo khách hàng | `rowId` | `(tenantId, normalizedSku)` |
| Đơn hàng từ đối tác | `internalId` | `(partnerId, externalOrderId)` |
| Giao dịch ngân hàng | `databaseId` | Mã giao dịch/định danh chống nhập trùng theo hợp đồng |
| Đăng ký khóa học | `enrollmentId` | `(studentId, courseId, term)` |
| Báo cáo ngày | `rowId` | `(accountId, date, metricType)` |

Không tự chọn một trường “có vẻ duy nhất” nếu nghiệp vụ chưa xác nhận. Chẳng hạn, cùng một SKU có thể hợp lệ ở **hai tenant khác nhau**; dùng SKU đơn lẻ làm khóa sẽ tạo **trùng giả** và làm mất dữ liệu.

### Trùng khóa không có nghĩa hai bản ghi hoàn toàn giống nhau

Hai dòng có thể:

- **Trùng hoàn toàn:** cùng khóa, cùng phiên bản, cùng mọi trường.
- **Trùng khóa nhưng khác phiên bản:** cần chọn bản mới nhất hoặc giữ lịch sử.
- **Trùng khóa và mâu thuẫn:** cùng phiên bản nhưng giá trị khác nhau; có thể phải báo lỗi.
- **Không trùng sau khi thêm phạm vi:** cùng SKU nhưng khác tenant là hai thực thể riêng.

Vì vậy, thao tác phát hiện trùng khóa **không tương đương** `stream.distinct()` trên toàn bộ record: `distinct()` xét `equals` của phần tử, còn khóa nghiệp vụ có thể chỉ là một số trường sau chuẩn hóa.

## 3. Định nghĩa khóa chuẩn hóa bằng record bất biến

Ta mô hình hóa dữ liệu nhập thành `StockRow` và khóa nghiệp vụ thành `BusinessKey`. Record giúp nhận được `equals` và `hashCode` theo các thành phần khóa, điều kiện cần để dùng làm khóa của `HashMap`.

~~~java
import java.util.Locale;
import java.util.Objects;

public class StockDomain {
    record StockRow(
        String rowId,
        String tenantId,
        String sku,
        long version,
        int quantity
    ) {}

    record BusinessKey(String tenantId, String sku) {}

    static String canonicalize(String text) {
        Objects.requireNonNull(text, "business key component");
        String result = text.strip().toUpperCase(Locale.ROOT);
        if (result.isEmpty()) {
            throw new IllegalArgumentException(
                "Thành phần khóa không được rỗng"
            );
        }
        return result;
    }

    static BusinessKey businessKey(StockRow row) {
        Objects.requireNonNull(row, "row");
        return new BusinessKey(
            canonicalize(row.tenantId()),
            canonicalize(row.sku())
        );
    }
}
~~~

Theo **quy ước của ví dụ**, khóa không phân biệt chữ hoa/thường và khoảng trắng đầu/cuối. Với dữ liệu dưới đây:

~~~java
StockDomain.StockRow a = new StockDomain.StockRow(
    "row-1", " T1 ", "book", 1, 10
);

StockDomain.StockRow b = new StockDomain.StockRow(
    "row-2", "t1", " BOOK ", 2, 8
);

System.out.println(
    StockDomain.businessKey(a).equals(StockDomain.businessKey(b))
); // true
~~~

`record BusinessKey` là một **value object**: hai khóa có cùng cặp thành phần chuẩn hóa thì bằng nhau. Không nên tạo khóa bằng nối chuỗi không có phân cách như `tenant + sku`, vì `("AB","C")` và `("A","BC")` đều thành `"ABC"`.

### Chuẩn hóa phải theo hợp đồng nghiệp vụ

Việc `toUpperCase(Locale.ROOT)` ở đây là **quy tắc SKU giả định**, không phải cách chuẩn hóa an toàn cho mọi loại ID. Ví dụ:

- Địa chỉ email có quy tắc phân biệt chữ hoa/thường và alias phụ thuộc nhà cung cấp; không tự ý loại dấu chấm hay đoạn sau dấu cộng.
- Một số mã đối tác phân biệt chữ hoa/thường; viết hoa mọi ký tự có thể tạo trùng giả.
- Unicode có nhiều cách biểu diễn hoặc ký tự tương tự về hình dạng; chuẩn hóa Unicode, dấu và khoảng trắng phải được quy định riêng nếu cần.
- SKU có số 0 đầu (như `"0012"`) không nên bị ép thành số `12` nếu hai mã khác nhau.
- Với định danh chuỗi, không tự bỏ dấu gạch nối hoặc khoảng trắng ở giữa nếu hợp đồng chưa cho phép.

**Quy tắc thiết kế:** Chuẩn hóa trước khi tạo khóa và dùng **cùng một hàm chuẩn hóa** khi xây chỉ mục lẫn khi truy vấn chỉ mục.

## 4. Cách 1 — Lập chỉ mục bằng toMap khi khóa phải duy nhất

Nếu hợp đồng đầu vào bảo đảm không có khóa trùng, `Collectors.toMap(keyMapper, valueMapper)` là cách ngắn gọn để tạo một chỉ mục:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public class UniqueIndex {
    record Product(String sku, String name) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("BOOK", "Sách"),
            new Product("PEN", "Bút"),
            new Product("PAD", "Sổ")
        );

        Map<String, Product> bySku = products.stream()
            .collect(Collectors.toMap(
                Product::sku,
                Function.identity()
            ));

        System.out.println(bySku.get("PEN").name()); // Bút
        System.out.println(bySku.size()); // 3
    }
}
~~~

`Function.identity()` giữ nguyên đối tượng làm **giá trị Map**. Key mapper có thể được thay bằng `StockDomain::businessKey` khi kiểu đầu vào là `StockRow`.

### Khóa trùng mặc định gây lỗi, không âm thầm ghi đè

~~~java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Collectors;

record Product(String sku, String name) {}

List<Product> duplicates = List.of(
    new Product("BOOK", "Sách A"),
    new Product("BOOK", "Sách B")
);

// Ném IllegalStateException khi có khóa BOOK trùng:
duplicates.stream().collect(Collectors.toMap(
    Product::sku,
    Function.identity()
));
~~~

Điểm mạnh của overload này là **phát hiện xung đột ngay trong quá trình thu thập**. Nó hợp lý khi bản ghi trùng **là lỗi và chương trình cần thất bại**. Tuy nhiên, ngoại lệ không phải một **báo cáo đầy đủ** về tất cả khóa trùng; nếu cần tổng hợp mọi xung đột để phản hồi cho người nhập dữ liệu, xem các mẫu `groupingBy` bên dưới.

`Collectors.toMap` mặc định không cam kết loại Map, thứ tự duyệt khóa, khả năng sửa đổi hoặc an toàn luồng của kết quả. Chỉ dựa vào giao diện `Map` trừ khi chọn `mapFactory` cụ thể.

## 5. Cách 2 — Đếm tần suất để phát hiện khóa trùng

Khi muốn biết **mọi khóa trùng** và số lần xuất hiện, `groupingBy(keyMapper, counting())` phù hợp. Kết quả là `Map<Key, Long>`; khóa có số đếm lớn hơn 1 là khóa trùng.

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public class CountDuplicates {
    record Row(String sku, int quantity) {}

    public static void main(String[] args) {
        List<Row> rows = List.of(
            new Row("BOOK", 2),
            new Row("PEN", 1),
            new Row("BOOK", 3),
            new Row("PAD", 1),
            new Row("PEN", 4)
        );

        Map<String, Long> frequencies = rows.stream()
            .collect(Collectors.groupingBy(
                Row::sku,
                Collectors.counting()
            ));

        Map<String, Long> duplicates = frequencies.entrySet().stream()
            .filter(entry -> entry.getValue() > 1)
            .collect(Collectors.toMap(
                Map.Entry::getKey,
                Map.Entry::getValue
            ));

        System.out.println(duplicates.get("BOOK")); // 2
        System.out.println(duplicates.get("PEN")); // 2
        System.out.println(duplicates.containsKey("PAD")); // false
    }
}
~~~

Đây là **phát hiện trùng**, chưa phải **giải quyết trùng**. Dữ liệu `BOOK` xuất hiện hai lần, nhưng bài toán còn phải trả lời: nên cộng quantity, chọn phiên bản mới nhất, giữ cả hai hay từ chối import?

### Đếm theo khóa đã chuẩn hóa, không phải chuỗi thô

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

// StockDomain.businessKey đã định nghĩa ở mục 3.
List<StockDomain.StockRow> rows = List.of(
    new StockDomain.StockRow("1", "T1", " book ", 1, 10),
    new StockDomain.StockRow("2", "t1", "BOOK", 2, 8),
    new StockDomain.StockRow("3", "T2", "BOOK", 1, 100)
);

Map<StockDomain.BusinessKey, Long> counts = rows.stream()
    .collect(Collectors.groupingBy(
        StockDomain::businessKey,
        Collectors.counting()
    ));

System.out.println(counts.get(
    new StockDomain.BusinessKey("T1", "BOOK")
)); // 2

System.out.println(counts.get(
    new StockDomain.BusinessKey("T2", "BOOK")
)); // 1
~~~

Chú ý khóa dùng để tra cứu trong Map phải ở dạng chuẩn hóa. Nếu lấy raw SKU `" book "` để gọi `get`, Map sẽ không tự chuẩn hóa lại tham số tra cứu.

## 6. Cách 3 — Giữ toàn bộ bản ghi trong nhóm trùng

Nếu bộ phận nhập liệu cần kiểm tra **những dòng cụ thể nào** gây xung đột, chỉ đếm là chưa đủ. Dùng `groupingBy` với downstream là `toList()`, rồi chỉ giữ các nhóm có kích thước lớn hơn một.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class DuplicateGroups {
    record Row(String rowId, String sku, int quantity) {}

    public static void main(String[] args) {
        List<Row> rows = List.of(
            new Row("r1", "BOOK", 2),
            new Row("r2", "PEN", 1),
            new Row("r3", "BOOK", 3),
            new Row("r4", "PAD", 1)
        );

        Map<String, List<Row>> grouped = rows.stream()
            .collect(Collectors.groupingBy(
                Row::sku,
                LinkedHashMap::new,
                Collectors.toList()
            ));

        Map<String, List<Row>> duplicateGroups =
            grouped.entrySet().stream()
                .filter(entry -> entry.getValue().size() > 1)
                .collect(Collectors.toMap(
                    Map.Entry::getKey,
                    entry -> List.copyOf(entry.getValue()),
                    (left, right) -> left,
                    LinkedHashMap::new
                ));

        System.out.println(
            duplicateGroups.get("BOOK").stream()
                .map(Row::rowId).toList()
        ); // [r1, r3]
    }
}
~~~

Các quyết định của ví dụ:

1. `LinkedHashMap::new` làm Map nhóm duyệt theo **thứ tự khóa được gặp lần đầu** trên Stream tuần tự có encounter order.
2. `toList()` giữ từng bản ghi thuộc nhóm, không loại thông tin.
3. `filter(size > 1)` xác định nhóm trùng, không phải chỉ trùng hoàn toàn theo record `equals`.
4. `List.copyOf(...)` tạo List không sửa đổi được cho báo cáo nhóm, đồng thời **cấm phần tử null**.
5. `toMap(..., LinkedHashMap::new)` giữ lại thứ tự duyệt khóa của các nhóm đã lọc.

Nếu không cần thứ tự khóa, có thể bỏ factory `LinkedHashMap`. Với dữ liệu lớn, lưu toàn bộ các nhóm có chi phí bộ nhớ gần theo **số bản ghi đầu vào**. Chỉ dùng đếm nếu đó là tất cả thông tin cần thu thập.

### Trùng hoàn toàn hay trùng khóa?

~~~java
record Row(String sku, int quantity) {}

List<Row> rows = List.of(
    new Row("BOOK", 2),
    new Row("BOOK", 3)
);

long exactDistinctCount = rows.stream().distinct().count(); // 2

long businessKeyDistinctCount = rows.stream()
    .map(Row::sku)
    .distinct()
    .count(); // 1
~~~

`distinct()` trên `Row` giữ cả hai vì `quantity` khác nhau. Sau khi `map(Row::sku)`, phép `distinct()` chỉ so sánh SKU. Tuy nhiên, một `Stream<String>` của các SKU riêng biệt **không** cho biết từng bản ghi gốc nào đã trùng. Muốn điều tra, giữ nhóm bản ghi như ví dụ trước.

## 7. Cách 4 — Chọn bản ghi đại diện bằng mergeFunction

Nếu có khóa trùng nhưng ứng dụng cần **một giá trị cuối cùng cho mỗi khóa**, dùng overload ba tham số:

~~~java
Collectors.toMap(
    keyMapper,
    valueMapper,
    mergeFunction
)
~~~

`mergeFunction` nhận hai giá trị đã được ánh xạ và quyết định giá trị giữ lại.

### 7.1. Chọn giá trị đầu hoặc cuối: chỉ khi thứ tự là quy tắc được định nghĩa

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Row(String key, String value) {}

List<Row> rows = List.of(
    new Row("K", "bản ghi đầu"),
    new Row("K", "bản ghi sau")
);

Map<String, String> firstWins = rows.stream()
    .collect(Collectors.toMap(
        Row::key,
        Row::value,
        (left, right) -> left
    ));

Map<String, String> lastWins = rows.stream()
    .collect(Collectors.toMap(
        Row::key,
        Row::value,
        (left, right) -> right
    ));

System.out.println(firstWins.get("K")); // bản ghi đầu
System.out.println(lastWins.get("K"));  // bản ghi sau
~~~

Trong ví dụ là **List tuần tự có encounter order**. Nếu nguồn không có thứ tự, hoặc dùng một collector `UNORDERED` như `toConcurrentMap`, cách chọn đại diện bằng vị trí `left/right` không tạo chính sách “đầu/ cuối theo thời gian” đáng tin cậy.

Hơn nữa, thứ tự trong file không nhất thiết là **thời gian cập nhật** của thực thể. Nếu nghiệp vụ nói “giữ bản ghi mới nhất”, phải so sánh `version`, `updatedAt` hay khóa ưu tiên có định nghĩa rõ ràng.

### 7.2. Chọn phiên bản mới nhất theo trường version

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class LatestByVersion {
    record Snapshot(String sku, long version, int quantity) {}

    public static void main(String[] args) {
        List<Snapshot> rows = List.of(
            new Snapshot("BOOK", 1, 10),
            new Snapshot("BOOK", 3, 8),
            new Snapshot("PEN", 2, 5)
        );

        BinaryOperator<Snapshot> chooseLatest =
            BinaryOperator.maxBy(
                Comparator.comparingLong(Snapshot::version)
            );

        Map<String, Snapshot> latest = rows.stream()
            .collect(Collectors.toMap(
                Snapshot::sku,
                Function.identity(),
                chooseLatest
            ));

        System.out.println(latest.get("BOOK").quantity()); // 8
        System.out.println(latest.get("BOOK").version());  // 3
    }
}
~~~

**Không cộng `quantity` của hai snapshot** nếu mỗi bản ghi mô tả trạng thái tồn kho ở một thời điểm khác nhau. Tổng `10 + 8 = 18` sẽ sai nghiệp vụ; kết quả cần là **8**, thuộc phiên bản mới nhất.

Nếu hai bản ghi cùng SKU có **cùng version nhưng quantity khác nhau**, `maxBy` với comparator chỉ theo version chưa đủ để định nghĩa đại diện. Có hai hướng hợp lý:

- **Báo xung đột** vì hai snapshot cùng version mâu thuẫn.
- **Đặt quy tắc phá hòa** dựa vào một trường ổn định và có ý nghĩa (ví dụ ID ưu tiên theo nguồn), nếu nghiệp vụ cho phép.

### 7.3. Xử lý tie một cách tường minh

Một merge function có thể từ chối trường hợp xung đột ở cùng version:

~~~java
import java.util.function.BinaryOperator;

BinaryOperator<LatestByVersion.Snapshot> chooseOrReject =
    (left, right) -> {
        if (left.version() == right.version()) {
            if (!left.equals(right)) {
                throw new IllegalStateException(
                    "Cùng SKU và version nhưng dữ liệu khác nhau"
                );
            }
            return left;
        }
        return left.version() > right.version() ? left : right;
    };
~~~

Dùng logic này khi snapshot có cùng version phải **hoàn toàn giống nhau** theo hợp đồng. Với các bản ghi có metadata kỹ thuật khác nhau nhưng payload tương đương, hãy so sánh những trường payload **có ý nghĩa nghiệp vụ**, không nhất thiết so sánh toàn bộ record.

Việc ném lỗi trong merge làm import dừng lại; nếu muốn trả **toàn bộ danh sách lỗi**, nên `groupingBy` để thu thập xung đột trước, rồi mới chọn đại diện ở bước sau.

## 8. Cách 5 — Gộp giá trị theo khóa khi dữ liệu là các phát sinh độc lập

Không phải mọi trùng khóa đều là lỗi. Nếu mỗi bản ghi là một **phát sinh độc lập**, nhiều dòng cùng SKU có thể cần **cộng dồn**.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class SoldUnitsIndex {
    record SaleLine(String sku, long soldUnits) {}

    public static void main(String[] args) {
        List<SaleLine> sales = List.of(
            new SaleLine("BOOK", 2),
            new SaleLine("PEN", 1),
            new SaleLine("BOOK", 3)
        );

        Map<String, Long> unitsBySku = sales.stream()
            .collect(Collectors.toMap(
                SaleLine::sku,
                SaleLine::soldUnits,
                Long::sum
            ));

        System.out.println(unitsBySku.get("BOOK")); // 5
        System.out.println(unitsBySku.get("PEN"));  // 1
    }
}
~~~

`Long::sum` là phép gộp **kết hợp** và **giao hoán** trên ngữ nghĩa số nguyên Java; không phụ thuộc thứ tự dòng theo cách phép chọn “bản ghi cuối” phụ thuộc thứ tự. Dù vậy, `long` vẫn có nguy cơ tràn nếu yêu cầu tổng toán học vượt miền biểu diễn.

### Phân biệt dữ liệu snapshot và dữ liệu event

| Dạng dữ liệu | Hai dòng cùng khóa | Phép xử lý thường hợp lý |
| --- | --- | --- |
| Snapshot số lượng tồn kho | Hai trạng thái của cùng thực thể | Chọn bản mới nhất hoặc báo xung đột |
| Dòng bán hàng | Hai phát sinh bán độc lập | Cộng lượng bán |
| Thông tin khách hàng | Hai cập nhật của một hồ sơ | So version/timestamp, xử lý tie |
| Đăng ký lớp học | Hai lần đăng ký cùng sinh viên/lớp/kỳ | Thường báo trùng hoặc giữ một đăng ký hợp lệ |
| Sự kiện giao dịch trùng request ID | Có thể là retry cùng giao dịch | Kiểm tra idempotency, không cộng tiền hai lần |

Không được chọn merge function chỉ vì nó **biên dịch được**. Nó phải thực thi đúng ý nghĩa của “trùng khóa” trong từng loại dữ liệu.

## 9. Khóa kết hợp và phạm vi định danh nhiều tầng

Một business key có thể là **nhiều trường**. Với tồn kho đa tenant, `sku` chỉ duy nhất trong phạm vi `tenantId`:

~~~java
record BusinessKey(String tenantId, String sku) {}

record Row(String tenantId, String sku, int quantity) {}

List<Row> rows = List.of(
    new Row("T1", "BOOK", 10),
    new Row("T2", "BOOK", 20)
);

Map<BusinessKey, Row> byBusinessKey = rows.stream()
    .collect(java.util.stream.Collectors.toMap(
        row -> new BusinessKey(row.tenantId(), row.sku()),
        java.util.function.Function.identity()
    ));

System.out.println(byBusinessKey.size()); // 2
~~~

Nếu chỉ dùng `Row::sku` làm khóa, collector hai tham số sẽ ném `IllegalStateException` do hai dòng có SKU `BOOK`. Nhưng đây là **hai dòng hợp lệ ở hai tenant**, nên xung đột đó là **trùng giả do định nghĩa khóa sai**.

### Khi nào dùng Map lồng nhau?

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Map<String, Row>> byTenantThenSku = rows.stream()
    .collect(Collectors.groupingBy(
        Row::tenantId,
        Collectors.toMap(
            Row::sku,
            java.util.function.Function.identity()
        )
    ));

System.out.println(byTenantThenSku.get("T1").get("BOOK").quantity()); // 10
~~~

Hai thiết kế đều có thể hợp lý:

- `Map<BusinessKey, Row>`: chỉ mục phẳng, lookup bằng một object khóa; thuận tiện cho so sánh, cache và chuyển đổi.
- `Map<Tenant, Map<Sku, Row>>`: diễn đạt cấu trúc phân cấp; thuận tiện khi cần lấy tất cả SKU của một tenant.

Ở Map lồng nhau, `toMap` phía trong vẫn ném lỗi nếu có **hai SKU trùng trong cùng tenant**. Nhờ đó, ranh giới định danh được phản ánh chính xác.

## 10. Kiểm soát null và dữ liệu không hợp lệ trước khi lập chỉ mục

Các collector không tự biết `null` có nghĩa gì trong nghiệp vụ. Đặc biệt:

- `groupingBy` trong JDK chuẩn không chấp nhận classifier trả khóa `null`.
- `Collectors.toUnmodifiableMap` cấm cả khóa và giá trị `null`.
- `Collectors.toMap` không nên được dùng như một hợp đồng chấp nhận `null` trên mọi triển khai. Nhiều trường hợp giá trị null dẫn tới `NullPointerException`.
- `List.of(...)` không chấp nhận phần tử null, trong khi nguồn như `Arrays.asList(...)` có thể chứa.

**Mẫu rõ ràng nhất** là quyết định chính sách đầu vào trước khi gọi collector: **từ chối**, **lọc**, hoặc **chuyển thành một trạng thái khóa có ý nghĩa**.

### 10.1. Lọc những dòng không thể lập khóa

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

record Row(String sku, int quantity) {}

List<Row> raw = Arrays.asList(
    new Row("BOOK", 3),
    null,
    new Row(null, 5),
    new Row("  ", 7),
    new Row("PEN", 1)
);

List<Row> valid = raw.stream()
    .filter(row -> row != null)
    .filter(row -> row.sku() != null && !row.sku().isBlank())
    .toList();

Map<String, Row> index = valid.stream()
    .collect(Collectors.toMap(
        row -> row.sku().strip().toUpperCase(Locale.ROOT),
        row -> row
    ));

System.out.println(valid.size()); // 2
System.out.println(index.keySet()); // Chứa BOOK và PEN.
~~~

Ở đây chọn **bỏ bản ghi lỗi** để minh họa. Trong quy trình tài chính hoặc tích hợp dữ liệu quan trọng, thường nên có báo cáo số dòng bị loại và nguyên nhân, hoặc dừng import. Không âm thầm biến null thành một khóa mặc định nếu nó có thể vô tình gộp nhiều thực thể khác nhau.

### 10.2. Phát hiện null trước khi so sánh

~~~java
// KHÔNG nên gọi row.sku().strip() trước khi
// bảo đảm row != null và row.sku() != null.
~~~

`String::strip` và `toUpperCase` cần đối tượng `String` hợp lệ. `filter(Objects::nonNull)` cho dòng nguồn phải đứng trước phép truy cập trường; sau đó kiểm tra các trường thành phần của khóa.

### 10.3. Quy trình chuẩn hóa không được giữ state ẩn

Hàm tạo khóa nên **thuần**: cùng bản ghi luôn tạo cùng khóa, không phụ thuộc biến đếm, thời gian hiện tại hay thứ tự callback. Trong parallel stream, mapper có thể chạy theo lịch bất kỳ; một key mapper thay đổi theo thời gian sẽ làm kết quả mất tính xác định.

## 11. Thứ tự đầu ra và lựa chọn Map phù hợp

`Map` phục vụ **tra cứu theo khóa**, không mặc nhiên phục vụ một danh sách có thứ tự. `Collectors.toMap` và `groupingBy` mặc định không cam kết thứ tự duyệt khóa.

| Yêu cầu | Lựa chọn | Lưu ý |
| --- | --- | --- |
| Tra cứu bình thường, không quan tâm thứ tự | `toMap(key, value, merge)` | Không dựa vào `map.keySet()` có thứ tự |
| Giữ thứ tự khóa gặp lần đầu từ List tuần tự | `toMap(key, value, merge, LinkedHashMap::new)` | Thứ tự chèn, không phải thứ tự version |
| Muốn khóa sắp theo comparator | `toMap(key, value, merge, TreeMap::new)` | Comparator quyết định khóa trùng |
| Map không sửa đổi được, dữ liệu không null | `toUnmodifiableMap(key, value, merge)` | Không cam kết thứ tự duyệt |
| Map có thể dùng để cập nhật đồng thời | `toConcurrentMap(...)` | Collector `UNORDERED`, phải xét tính độc lập thứ tự |

Ví dụ tạo index theo thứ tự xuất hiện của khóa:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Row(String sku, int quantity) {}

List<Row> rows = List.of(
    new Row("PEN", 1),
    new Row("BOOK", 2),
    new Row("PEN", 3)
);

Map<String, Integer> inFirstSeenOrder = rows.stream()
    .collect(Collectors.toMap(
        Row::sku,
        Row::quantity,
        Integer::sum,
        LinkedHashMap::new
    ));

System.out.println(inFirstSeenOrder); // {PEN=4, BOOK=2}
~~~

Dữ liệu kết quả là Map có thể sửa được. Nếu muốn công bố index **không cho sửa cấu trúc** nhưng vẫn duyệt theo thứ tự chèn, có thể dùng:

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;

Map<String, Integer> published =
    Collections.unmodifiableMap(
        new LinkedHashMap<>(inFirstSeenOrder)
    );
~~~

`Collections.unmodifiableMap` là view không cho sửa qua tham chiếu wrapper; việc tạo `new LinkedHashMap<>(...)` trước giúp tách cấu trúc khỏi Map xây dựng ban đầu. Tuy nhiên, các object giá trị mutable (nếu có) vẫn có thể thay đổi; đây **không tự động là bất biến sâu**.

## 12. Song song, đặc tính CONCURRENT của Collector và merge function

Khi dữ liệu lớn, có thể cân nhắc `parallelStream()`. Nhưng tính đúng phải được bảo đảm trước khi tối ưu.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record SaleLine(String sku, long units) {}

List<SaleLine> sales = List.of(
    new SaleLine("BOOK", 2),
    new SaleLine("BOOK", 3),
    new SaleLine("PEN", 1)
);

Map<String, Long> totals = sales.parallelStream()
    .collect(Collectors.toMap(
        SaleLine::sku,
        SaleLine::units,
        Long::sum
    ));

System.out.println(totals.get("BOOK")); // 5
~~~

`toMap` **không** là concurrent collector, nhưng có thể dùng trên parallel stream. Framework có thể tích lũy vào các Map trung gian rồi **hợp nhất** chúng. `toConcurrentMap` là collector có `CONCURRENT` và `UNORDERED`, phù hợp khi muốn một `ConcurrentMap` và không cần thứ tự.

~~~java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> concurrentTotals =
    sales.parallelStream().collect(
        Collectors.toConcurrentMap(
            SaleLine::sku,
            SaleLine::units,
            Long::sum
        )
    );
~~~

**Không dùng** `(left, right) -> right` làm “lấy bản ghi mới nhất” trong collector `UNORDERED`. Để kết quả nhất quán, dùng một hàm gộp **kết hợp** và, nếu thứ tự có thể thay đổi, nên **giao hoán** hoặc chọn đại diện theo khóa so sánh ổn định.

### 12.1. Khi cần giữ tất cả nhóm trùng trong song song

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.List;
import java.util.stream.Collectors;

ConcurrentMap<String, List<SaleLine>> grouped =
    sales.parallelStream()
        .collect(Collectors.groupingByConcurrent(
            SaleLine::sku
        ));
~~~

`groupingByConcurrent` là collector `CONCURRENT` và `UNORDERED`. Danh sách trong nhóm không được bảo đảm giữ encounter order hoặc hỗ trợ các sửa đổi đồng thời tùy ý **sau khi thu thập**. Chọn collector tuần tự và loại Map có thứ tự nếu cần báo cáo điều tra trùng theo đúng trình tự nguồn.

### 12.2. Chi phí thực tế

Các khóa “nóng” có nhiều bản ghi trùng khiến nhiều cập nhật cạnh tranh cùng một entry. Thời gian tính hash, chuẩn hóa khóa, merge object, GC và kết hợp Map có thể lớn hơn lợi ích song song. Không có ngưỡng kích thước cố định để `parallelStream` luôn nhanh hơn; hãy đo dữ liệu đại diện.

## 13. Một quy trình nhập liệu hoàn chỉnh: giữ index và báo cáo trùng

**Bài toán tổng hợp:** Dữ liệu tồn kho gồm tenant, SKU, version, quantity và ID dòng nhập. Đầu vào có thể có dòng `null` hoặc trường khóa không hợp lệ. Quy tắc:

1. Dòng thiếu tenant, SKU, rowId hoặc có version/quantity âm bị loại vào số đếm lỗi.
2. SKU và tenant được chuẩn hóa bằng `strip().toUpperCase(Locale.ROOT)` theo quy tắc bài.
3. Hai dòng cùng `BusinessKey(tenant, sku)` được ghi nhận là trùng, dù version khác nhau.
4. Chỉ mục cuối cùng giữ snapshot có version **cao nhất**.
5. Nếu version bằng nhau, bài minh họa phá hòa bằng `rowId` theo thứ tự chữ cái để kết quả xác định. **Trong hệ thống thật, cần xác nhận chính sách này**, hoặc báo lỗi nếu payload mâu thuẫn.
6. Khóa Map được duyệt theo lần xuất hiện đầu trong danh sách đầu vào; kết quả được công bố dưới dạng Map không cho sửa cấu trúc.

### Lời giải Java 17+ đầy đủ

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class StockImport {
    record StockRow(
        String rowId,
        String tenantId,
        String sku,
        long version,
        int quantity
    ) {}

    record BusinessKey(String tenantId, String sku) {}

    record ImportResult(
        Map<BusinessKey, StockRow> latestByKey,
        Map<BusinessKey, List<StockRow>> duplicateGroups,
        long rejectedRows
    ) {}

    static boolean isValid(StockRow row) {
        return row != null
            && row.rowId() != null && !row.rowId().isBlank()
            && row.tenantId() != null && !row.tenantId().isBlank()
            && row.sku() != null && !row.sku().isBlank()
            && row.version() >= 0
            && row.quantity() >= 0;
    }

    static String canonicalize(String text) {
        Objects.requireNonNull(text, "text");
        return text.strip().toUpperCase(Locale.ROOT);
    }

    static BusinessKey keyOf(StockRow row) {
        return new BusinessKey(
            canonicalize(row.tenantId()),
            canonicalize(row.sku())
        );
    }

    static ImportResult analyze(List<StockRow> source) {
        Objects.requireNonNull(source, "source");

        List<StockRow> valid = source.stream()
            .filter(StockImport::isValid)
            .toList();

        long rejectedCount = source.size() - valid.size();

        // Giữ toàn bộ nguồn của các khóa trùng để điều tra.
        Map<BusinessKey, List<StockRow>> grouped = valid.stream()
            .collect(Collectors.groupingBy(
                StockImport::keyOf,
                LinkedHashMap::new,
                Collectors.toList()
            ));

        Map<BusinessKey, List<StockRow>> duplicateGroups =
            grouped.entrySet().stream()
                .filter(entry -> entry.getValue().size() > 1)
                .collect(Collectors.toMap(
                    Map.Entry::getKey,
                    entry -> List.copyOf(entry.getValue()),
                    (left, right) -> left,
                    LinkedHashMap::new
                ));

        Comparator<StockRow> newer = Comparator
            .comparingLong(StockRow::version)
            .thenComparing(StockRow::rowId);

        BinaryOperator<StockRow> chooseLatest =
            BinaryOperator.maxBy(newer);

        Map<BusinessKey, StockRow> latest = valid.stream()
            .collect(Collectors.toMap(
                StockImport::keyOf,
                Function.identity(),
                chooseLatest,
                LinkedHashMap::new
            ));

        return new ImportResult(
            Collections.unmodifiableMap(
                new LinkedHashMap<>(latest)
            ),
            Collections.unmodifiableMap(
                new LinkedHashMap<>(duplicateGroups)
            ),
            rejectedCount
        );
    }

    public static void main(String[] args) {
        List<StockRow> incoming = Arrays.asList(
            new StockRow("r1", "T1", " book ", 1, 10),
            new StockRow("r2", "t1", "BOOK", 2, 8),
            new StockRow("r3", "T1", "PEN", 1, 5),
            new StockRow("r4", "T2", "BOOK", 1, 100),
            new StockRow("r5", "T1", " ", 1, 1),
            null
        );

        ImportResult report = analyze(incoming);

        BusinessKey t1Book = new BusinessKey("T1", "BOOK");
        BusinessKey t2Book = new BusinessKey("T2", "BOOK");

        System.out.println(report.rejectedRows()); // 2
        System.out.println(report.latestByKey().size()); // 3

        System.out.println(
            report.latestByKey().get(t1Book).quantity()
        ); // 8 (version 2)

        System.out.println(
            report.latestByKey().get(t2Book).quantity()
        ); // 100 (tenant khác)

        System.out.println(
            report.duplicateGroups().get(t1Book)
                .stream().map(StockRow::rowId).toList()
        ); // [r1, r2]
    }
}
~~~

### Tại sao phải tính hai cấu trúc riêng?

- `groupingBy` giữ đủ các bản ghi gốc của khóa trùng, phục vụ chẩn đoán.
- `toMap` với `mergeFunction` giữ một bản ghi đại diện, phục vụ tra cứu thường xuyên.
- `LinkedHashMap` giúp báo cáo dễ theo dõi theo **thứ tự xuất hiện đầu của các khóa** trong input `List` tuần tự.
- `List.copyOf` trong báo cáo trùng tạo danh sách không sửa đổi được; record `StockRow` cũng chỉ chứa các giá trị bất biến trong ví dụ.
- `rejectedCount` giữ tín hiệu số lượng dữ liệu đầu vào bị loại; hệ thống thực có thể lưu thêm lý do lỗi của từng dòng.

Ở đoạn trên, `StockRow` được giữ nguyên như dữ liệu nguồn, còn **khóa trong Map** đã được chuẩn hóa. Đừng gọi `latestByKey().get(new BusinessKey("t1", " book "))` và mong Map tự chuẩn hóa query. Hãy cung cấp hàm `lookupKey(tenant, sku)` dùng đúng `canonicalize` trước khi tra cứu.

### Nếu không thể chấp nhận tie tùy ý

Quy tắc phá hòa `thenComparing(StockRow::rowId)` giúp lựa chọn nhất quán nhưng không đảm bảo đúng nghiệp vụ. Nếu cùng `version` mà quantity khác nhau là **lỗi xung đột**, hãy phát hiện ở các nhóm trùng và báo lỗi **trước** khi tạo index cuối. Không để một quyết định kỹ thuật che mất vi phạm dữ liệu.

## 14. Kiểm thử tính đúng của khóa và chỉ mục

Kiểm thử nên tập trung vào **ngữ nghĩa nghiệp vụ**, không vào thứ tự mà một `HashMap` tình cờ in ra. Các tình huống quan trọng:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Cùng tenant, SKU khác chữ hoa/thường | Thành cùng khóa nếu chính sách là không phân biệt |
| Cùng SKU, khác tenant | Hai khóa khác nhau |
| Cùng khóa, version mới hơn | Chọn đúng version cao nhất |
| Cùng khóa, version bằng nhau nhưng payload khác | Báo xung đột hoặc áp dụng tie policy đã định |
| Khóa bị null/rỗng | Theo chính sách: từ chối, không âm thầm lập khóa |
| Nguồn rỗng | Index và báo cáo trùng rỗng |
| Một dòng hợp lệ | Có một entry, không có nhóm trùng |
| Nhiều bản ghi trùng | Có một index entry và nhóm trùng với đủ bản ghi |
| Data là phát sinh độc lập | Gộp bằng phép cộng nếu đúng miền nghiệp vụ |
| Parallel/unordered | Không chọn đại diện dựa vào lịch thread |
| Key mutable | Không sử dụng key có trạng thái thay đổi sau khi đưa vào Map |

### Bài kiểm tra độc lập với thứ tự HashMap

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class IndexAssertions {
    record Row(String tenant, String sku, int quantity) {}
    record Key(String tenant, String sku) {}

    static Key keyOf(Row row) {
        return new Key(row.tenant(), row.sku());
    }

    public static void main(String[] args) {
        List<Row> rows = List.of(
            new Row("T1", "BOOK", 1),
            new Row("T2", "BOOK", 2),
            new Row("T1", "BOOK", 3)
        );

        Map<Key, Long> counts = rows.stream()
            .collect(Collectors.groupingBy(
                IndexAssertions::keyOf,
                Collectors.counting()
            ));

        if (counts.size() != 2) {
            throw new AssertionError("Sai số khóa phân biệt");
        }
        if (!Long.valueOf(2).equals(
                counts.get(new Key("T1", "BOOK")))) {
            throw new AssertionError("Không phát hiện đúng trùng khóa");
        }
        if (!Long.valueOf(1).equals(
                counts.get(new Key("T2", "BOOK")))) {
            throw new AssertionError("Gộp nhầm dữ liệu giữa tenant");
        }

        System.out.println("PASS");
    }
}
~~~

Bài kiểm tra này dùng record `Key` để xác định tính bằng nhau của khóa qua **hai trường**. Trong phiên bản sản xuất, thêm kiểm thử chuẩn hóa, dữ liệu null, collision, version tie và giới hạn số.

### Có cần so sánh Stream tuần tự và song song?

Có, nếu định dùng parallel. Với phép tổng kết hợp/giao hoán, so sánh Map theo nội dung bằng `Map.equals` là cách hợp lý. Với chính sách chọn latest theo `version`, phải xác định **toàn bộ thứ tự so sánh** để không phụ thuộc cách phân nhóm. Không đo tính đúng bằng số lượng log trong `peek` hoặc thứ tự callback.

## 15. Hiệu năng và giới hạn của cách tiếp cận

### 15.1. Lookup Map thay cho quét List lặp lại

Nếu cần tìm `k` bản ghi từ một List gồm `n` dòng, cách `list.stream().filter(...).findFirst()` lặp lại có thể tốn nhiều lần quét. Lập Map một lần giúp truy vấn theo khóa bằng `get` thường nhanh hơn đáng kể khi có nhiều lần lookup.

Chi phí nhìn chung:

- Xây `HashMap` qua `toMap`: trung bình tỷ lệ với số phần tử đầu vào khi hash và equality hoạt động tốt.
- Mỗi lần `Map.get`: trung bình gần O(1) đối với HashMap với điều kiện phân bố hash tốt.
- `groupingBy(..., toList())`: cần giữ nhiều bản ghi, bộ nhớ theo quy mô nguồn.
- `TreeMap`: có thứ tự theo comparator, các thao tác tìm/chèn thường O(log k) với `k` khóa.

Đây là mô tả định hướng, không phải bảo đảm thời gian cố định của Stream API. Trường hợp hash collision nặng, phép chuẩn hóa đắt hoặc memory/GC giới hạn có thể thay đổi hiệu năng thực tế.

### 15.2. Không xây cả danh sách nhóm nếu chỉ cần đếm

`groupingBy(key, counting())` giữ giá trị đếm theo mỗi khóa, trong khi `groupingBy(key, toList())` giữ **toàn bộ dòng** trong từng nhóm. Nếu chỉ cần biết liệu có trùng hay không và không cần bản ghi chi tiết, đếm thường tiết kiệm bộ nhớ hơn.

Nếu dữ liệu rất lớn và phải tìm **tất cả nhóm trùng**, hãy cân nhắc xử lý theo lô hoặc sử dụng cơ sở dữ liệu/engine chuyên dụng. Một Map trong RAM không thay thế các ràng buộc và chỉ mục bền vững trên hệ thống lưu trữ.

### 15.3. Chỉ mục trong RAM không bảo đảm tính duy nhất giao dịch

Hai tiến trình có thể cùng đọc dữ liệu, mỗi bên thấy “không trùng”, rồi đồng thời ghi vào database. Kiểm tra trùng trong Stream chỉ là **kiểm tra dữ liệu trong phạm vi đang có**; nó không ngăn race condition giữa nhiều phiên nhập.

Với yêu cầu duy nhất bền vững, cần **unique constraint/index** hoặc thao tác upsert/transaction phù hợp tại tầng lưu trữ. Stream có thể phát hiện lỗi sớm và tạo báo cáo thân thiện, nhưng không thay thế bảo đảm nhất quán của database.

## 16. Những nhầm lẫn thường gặp

### Nhầm lẫn 1: `distinct()` là đủ để phát hiện mọi bản ghi trùng theo nghiệp vụ

`distinct()` xét `equals` của phần tử. Nếu khóa nghiệp vụ là tenant + SKU, phải ánh xạ sang `BusinessKey` hoặc phân nhóm theo hàm tạo khóa; hai record khác version vẫn có thể trùng khóa.

### Nhầm lẫn 2: `toMap` tự ghi đè bản ghi trùng

Overload hai tham số ném `IllegalStateException` khi khóa trùng. Muốn giải quyết trùng phải truyền `mergeFunction` và xác định quy tắc nghiệp vụ.

### Nhầm lẫn 3: dữ liệu snapshot có thể cộng như giao dịch phát sinh

Hai số lượng tồn kho 10 rồi 8 là hai trạng thái, không phải tổng 18. Hãy phân biệt snapshot với event trước khi chọn `Integer::sum` hoặc `Long::sum`.

### Nhầm lẫn 4: chỉ cần chuẩn hóa khi nhập, không cần khi truy vấn

Map dùng `equals`/`hashCode` trên khóa được cung cấp. Query `" book "` không tự thành `"BOOK"`. Dùng chung hàm chuẩn hóa cho cả tạo và tra cứu khóa.

### Nhầm lẫn 5: chọn SKU làm khóa cho mọi tenant

Một SKU có thể tồn tại ở nhiều tenant. Dùng composite key để tránh phát hiện trùng giả và ghi đè thông tin tenant khác.

### Nhầm lẫn 6: `(left, right) -> right` luôn là bản ghi mới nhất

Thứ tự xử lý và lịch thread không phải timestamp nghiệp vụ. So sánh version/timestamp có chính sách tie rõ ràng.

### Nhầm lẫn 7: Map không sửa được nghĩa là phần tử bất biến sâu

`Map.copyOf` và `Collections.unmodifiableMap` ngăn chỉnh sửa cấu trúc qua Map kết quả, nhưng nếu value là object mutable, trường bên trong vẫn có thể thay đổi. Hãy chọn value object bất biến hoặc sao chép phòng vệ khi cần snapshot thật.

### Nhầm lẫn 8: chuyển sang `parallelStream()` luôn tăng tốc

Chi phí merge, chia việc, contention ở khóa nóng, cấp phát và GC có thể khiến song song chậm hơn. Trước khi benchmark, hãy bảo đảm mapper thuần và phép gộp hợp lệ.

## 17. Bảng chọn giải pháp cho từng mục tiêu

| Mục tiêu | Pipeline hoặc collector gợi ý | Chú ý |
| --- | --- | --- |
| Lập index khi khóa phải duy nhất | `toMap(key, identity())` | Từ chối khóa trùng |
| Tìm mọi khóa xuất hiện hơn một lần | `groupingBy(key, counting())` rồi lọc `count > 1` | Không giữ payload |
| Giữ tất cả dòng gây trùng | `groupingBy(key, toList())` rồi lọc nhóm `size > 1` | Tốn bộ nhớ hơn |
| Chọn snapshot mới nhất | `toMap(key, identity(), maxBy(versionComparator))` | Cần xử lý tie |
| Gộp phát sinh độc lập | `toMap(key, amountMapper, sumOperator)` | Kiểm tra overflow/đơn vị |
| Lập index theo nhiều trường | `record BusinessKey(...)` làm key | Bảo đảm chuẩn hóa và equality |
| Giữ thứ tự xuất hiện đầu của khóa | `toMap(..., LinkedHashMap::new)` | Nguồn tuần tự ordered |
| Sắp khóa theo comparator | `toMap(..., TreeMap::new)` | Comparator quyết định tính tương đương |
| Thu vào ConcurrentMap | `toConcurrentMap(...)` | `UNORDERED`, không dựa vào last-wins |
| Tạo nhiều nhóm đồng thời | `groupingByConcurrent(...)` | Không giữ encounter order |
| Công bố Map không cho sửa | Tạo bản sao rồi bọc, hoặc `toUnmodifiableMap` khi phù hợp | Chính sách null, thứ tự và value mutable |
| Duy trì uniqueness xuyên giao dịch | Unique constraint/index ở database | Stream không đủ bảo đảm |

## 18. Câu hỏi tự kiểm tra và bài mở rộng

1. **Khóa kỹ thuật khác khóa nghiệp vụ thế nào?** Khóa kỹ thuật nhận diện bản ghi lưu trữ; khóa nghiệp vụ nhận diện thực thể theo quy tắc domain.
2. **Vì sao `(tenantId, sku)` tốt hơn chỉ `sku` trong hệ thống đa tenant?** Cùng SKU của hai tenant khác nhau không phải trùng thực thể.
3. **`Collectors.toMap(key, value)` làm gì khi khóa trùng?** Ném `IllegalStateException`.
4. **Muốn biết toàn bộ khóa trùng và số lần, dùng gì?** `groupingBy(key, counting())` rồi lọc những số đếm lớn hơn 1.
5. **Muốn xem dòng dữ liệu nào gây xung đột, dùng gì?** `groupingBy(key, toList())` rồi lọc nhóm trùng.
6. **Hai record khác `quantity` nhưng cùng tenant/SKU có thể bị coi là trùng không?** Có, nếu business key chỉ gồm tenant/SKU.
7. **`distinct()` trên toàn record có phát hiện được trùng khóa bất chấp version không?** Không nhất thiết; `distinct` dựa vào `equals` của record.
8. **Vì sao chuẩn hóa khóa phải dùng cả khi xây index và khi lookup?** Vì Map không tự chuẩn hóa query.
9. **Vì sao không dùng một chuỗi nối không phân cách làm composite key?** Các cặp thành phần khác nhau có thể tạo cùng chuỗi kết quả.
10. **Giữ dòng có version lớn nhất có phù hợp để gộp doanh số của nhiều giao dịch không?** Không; doanh số phát sinh thường cần cộng hoặc giữ từng giao dịch tùy mô hình.
11. **Vì sao version bằng nhau cần chính sách phá hòa hoặc báo xung đột?** Vì comparator chỉ theo version có thể không xác định một đại diện hợp lệ duy nhất.
12. **`Long::sum` có đảm bảo không tràn long không?** Không.
13. **Có nên dựa vào thứ tự in ra của `Collectors.toMap` mặc định không?** Không.
14. **Khi nào dùng `LinkedHashMap::new`?** Khi yêu cầu duyệt khóa theo thứ tự chèn.
15. **`toConcurrentMap` có bảo đảm giữ encounter order không?** Không; đây là collector `UNORDERED`.
16. **Có được đưa `null` vào key mapper rồi kỳ vọng mọi collector xử lý giống nhau không?** Không; cần chính sách rõ ràng trước collect.
17. **Tại sao không lưu mọi List nhóm nếu chỉ cần phát hiện trùng?** Vì lưu payload làm tăng chi phí bộ nhớ; đếm có thể đủ.
18. **Kiểm tra trùng bằng Stream có thay thế unique constraint ở cơ sở dữ liệu không?** Không; không bảo đảm uniqueness xuyên tiến trình/giao dịch.
19. **Khi nào nên ưu tiên vòng lặp hơn Stream?** Khi cần dừng ngay với thông tin lỗi cụ thể, tích lũy nhiều cấu trúc có side effect cần kiểm soát hoặc thao tác phức tạp khó đọc bằng collector lồng nhau.
20. **Bản ghi immutable và BusinessKey immutable có giúp gì?** Giữ `equals`/`hashCode` và dữ liệu index ổn định; tránh mutation phá lookup.

### Bài mở rộng A — Phát hiện xung đột version

Với các snapshot cùng `BusinessKey`, viết quy tắc: version lớn hơn thắng; nếu version bằng nhau mà quantity khác thì báo lỗi. Thiết kế kiểm thử với ba bản ghi cùng khóa, hai version bằng nhau và có quantity khác.

### Bài mở rộng B — Không loại dữ liệu lỗi âm thầm

Thay `rejectedRows` bằng `List<ValidationError>` chứa `rowId` và lý do: tenant thiếu, SKU thiếu, quantity âm hoặc version âm. Thiết kế collector hoặc các bước phân loại sao cho bản ghi lỗi không bị đưa vào Map cuối.

### Bài mở rộng C — Khóa nghiệp vụ theo ngày

Tạo `record DailyKey(String accountId, LocalDate day)`. Nhập giao dịch, nhóm theo ngày và tài khoản, tính tổng với `BigDecimal`. Thử trường hợp timestamp ở múi giờ khác nhau: phải quyết định “ngày” theo timezone nghiệp vụ trước khi lập khóa.

### Bài mở rộng D — So sánh cách xử lý song song

Dùng dữ liệu 100.000 dòng có số khóa phân biệt thấp và cao. So sánh kết quả `toMap`, `toConcurrentMap` với `Long::sum`, kiểm tra Map bằng `equals`, rồi benchmark. Không mặc định concurrent nhanh hơn; giải thích tác động của khóa nóng.

**Ghi nhớ:** Lập chỉ mục đúng bắt đầu từ **định nghĩa khóa nghiệp vụ** và **quy tắc chuẩn hóa**, không bắt đầu từ lời gọi `toMap`. `toMap` phù hợp khi cần một kết quả cho mỗi khóa và có chính sách xử lý xung đột; `groupingBy` phù hợp khi cần đếm hoặc lưu đủ nhóm trùng để kiểm tra. Hãy phân biệt snapshot với phát sinh độc lập, xử lý `null` và tie rõ ràng, bảo đảm phép merge đúng miền dữ liệu và nhớ rằng chỉ mục Stream trong RAM không thay thế ràng buộc nhất quán của hệ thống lưu trữ.
