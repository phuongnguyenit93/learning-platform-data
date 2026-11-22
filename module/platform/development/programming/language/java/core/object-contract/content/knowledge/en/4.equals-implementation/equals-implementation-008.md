# Không thay đổi trạng thái hoặc phụ thuộc thời gian trong `equals()`

## 1. Mục tiêu khi cài đặt `equals()`

Khi override `Object.equals(Object)`, hãy xem phương thức này như một phép **quan sát quan hệ bằng nhau** giữa hai đối tượng: đọc thông tin cần so sánh, tính toán và trả về `boolean`. Việc gọi `equals()` không nên làm thay đổi trạng thái quan sát được của đối tượng hoặc hệ thống; kết quả cũng không nên phụ thuộc vào giờ hiện tại, số lần gọi hoặc các tác động bên ngoài không liên quan đến giá trị cần so sánh.

Điều này liên quan chặt chẽ đến **tính nhất quán (consistency)** trong hợp đồng `equals`: với hai tham chiếu khác `null` là `x` và `y`, những lần gọi `x.equals(y)` lặp lại phải trả về cùng `true` hoặc cùng `false`, **miễn là không có thông tin được dùng cho phép so sánh trên các đối tượng thay đổi**.

Ba điều cần phân biệt:

1. **Quy định của hợp đồng:** Tính nhất quán có điều kiện nêu trên là một yêu cầu chính thức của `Object.equals`. Các tính chất phản xạ, đối xứng, bắc cầu và hành vi với `null` cũng phải được giữ.
2. **Nguyên tắc thiết kế:** Tránh side effect trong `equals` là một thực hành mạnh để giúp API an toàn và dễ dự đoán; Java không có một câu lệnh đặc biệt nào tự động cấm mọi side effect trong phương thức.
3. **Tính ổn định của dữ liệu:** Nếu một trường **được dùng để so sánh** thực sự thay đổi, kết quả `equals` có thể thay đổi theo trường đó mà không tự động vi phạm phát biểu nhất quán có điều kiện. Nhưng dùng đối tượng có khóa bình đẳng thay đổi trong `HashMap`/`HashSet` rất dễ làm hỏng việc tra cứu.

Đề bài nhấn mạnh hai nguồn rủi ro phải tránh: **`equals()` tự sửa trạng thái** và **`equals()` phụ thuộc vào thời gian**.

## 2. Tại sao `equals()` không nên có side effect?

*Side effect* là tác động ngoài việc tạo giá trị trả về, chẳng hạn:

- Tăng biến đếm trong đối tượng, đổi cờ `visited` hoặc cập nhật `lastCheckedAt`.
- Ghi hoặc xóa phần tử trong một collection, thay đổi bộ nhớ đệm quan sát được, cập nhật database, gửi thông báo hay gọi một API có tác động ghi.
- Thay đổi trạng thái chung (`static`), biến toàn cục, `ThreadLocal` hoặc trạng thái của đối tượng được so sánh còn lại.

Ngay cả side effect không làm kết quả `equals` đổi ngay lập tức cũng gây bất ngờ: đọc dữ liệu bằng `contains`, `remove`, `get` hoặc một kiểm tra bình đẳng lại có thể sửa dữ liệu. Nếu side effect tác động tới các trường tham gia `equals`/`hashCode`, lần gọi sau còn có thể cho kết quả khác, hoặc khóa trong cấu trúc băm trở nên không truy cập được như mong đợi.

Ví dụ **không nên viết**:

```java
@Override
public boolean equals(Object other) {
    comparisons++; // Tác dụng phụ: mỗi phép so sánh làm đổi trạng thái.
    if (this == other) {
        return true;
    }
    if (!(other instanceof Customer that)) {
        return false;
    }
    return id == that.id;
}
```

Đây là **mảnh mã minh họa** nằm trong một lớp có trường `comparisons` và `id`, không phải chương trình biên dịch độc lập. Trường `comparisons` có thể không tham gia so sánh nên đoạn code *chưa chắc* vi phạm tính nhất quán chính thức. Nhưng việc gọi `equals` làm tăng `comparisons` vẫn là một thiết kế khó dùng đúng; đừng đặt logic nghiệp vụ, phép ghi hoặc điều kiện quyết định bình đẳng dựa trên số lần đã so sánh vào đây.

Nếu cần metrics cho hệ thống, nên thu thập ở tầng gọi hoặc hệ thống quan sát bên ngoài; không biến `equals` thành một thao tác ghi trên đối tượng giá trị.

## 3. Vì sao không được dùng thời gian hiện tại để quyết định bằng nhau?

Các cách viết dùng `System.currentTimeMillis()`, `Instant.now()`, thời điểm hết hạn, hôm nay/ngày mai hoặc một bộ đếm thời gian biến đổi làm cho **cùng hai đối tượng với cùng dữ liệu** có thể được coi là bằng nhau ở thời điểm này và khác nhau ở thời điểm khác.

Ví dụ sai về ý tưởng:

```java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof SessionKey that)) {
        return false;
    }
    return token.equals(that.token)
            && System.currentTimeMillis() < expiresAtMillis
            && System.currentTimeMillis() < that.expiresAtMillis;
}
```

Đây là **mảnh mã minh họa** giả sử có các trường `token`, `expiresAtMillis` trong lớp `SessionKey`. Cùng dữ liệu không đổi nhưng kết quả chuyển từ `true` sang `false` khi thời gian qua mốc hết hạn. Cách cài đặt còn lấy đồng hồ hai lần, nên hai phép đọc có thể lệch nhau ngay ở ranh giới. Không nên dùng trạng thái *còn hiệu lực hay không* làm một phần của danh tính logic trong `equals`.

Thay vào đó:

- Dùng `equals` để so sánh **danh tính/giá trị ổn định**, ví dụ `token` hoặc bộ `(tenantId, sessionId)`.
- Tách điều kiện thời gian thành phương thức riêng như `isExpired(Clock clock)` hoặc `isValidAt(Instant now)`. Thời gian là **đầu vào tường minh** của phép kiểm tra hiệu lực.
- Khi muốn so sánh một thời điểm là **giá trị thuộc tính** (ví dụ `createdAt` đã lưu và không đổi), việc so sánh `createdAt` của hai đối tượng là hoàn toàn khác với việc hỏi `Instant.now()` trong `equals`. Giá trị timestamp bất biến có thể là một phần của bình đẳng nếu mô hình nghiệp vụ thực sự yêu cầu.

Nói chính xác, phát biểu nhất quán của `Object.equals` được điều kiện hóa trên thông tin được dùng để so sánh không thay đổi. Một đồng hồ bên ngoài đang chạy làm thông tin tính toán thay đổi; đó chính là lý do **không thiết kế bình đẳng phụ thuộc vào đồng hồ**, dù chỉ tranh luận theo câu chữ hợp đồng chưa đủ để kết luận mọi ví dụ sử dụng thời gian đều vi phạm một điều khoản cụ thể.

## 4. Ví dụ hoàn chỉnh, chạy bằng Java 17

Ví dụ có ba kiểu đối tượng:

- `StableKey`: so sánh theo các trường `final` và không phát sinh side effect.
- `CountingKey`: gọi `equals` làm tăng bộ đếm trong đối tượng (ví dụ **không nên dùng**).
- `TimedKey`: so sánh bị lệ thuộc vào đồng hồ được giả lập, cho phép kiểm chứng kết quả bằng nhau thay đổi theo thời gian mà không phải chờ thật.

Tạo tệp **`EqualsPurityDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class EqualsPurityDemo {
    static final class StableKey {
        private final String tenant;
        private final long id;

        StableKey(String tenant, long id) {
            this.tenant = tenant;
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof StableKey that)) {
                return false;
            }
            return id == that.id
                    && Objects.equals(tenant, that.tenant);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenant, id);
        }
    }

    static final class CountingKey {
        private final String code;
        private int comparisons;

        CountingKey(String code) {
            this.code = code;
        }

        int comparisonCount() {
            return comparisons;
        }

        @Override
        public boolean equals(Object other) {
            comparisons++; // KHÔNG NÊN: equals có side effect.
            if (this == other) {
                return true;
            }
            if (!(other instanceof CountingKey that)) {
                return false;
            }
            return Objects.equals(code, that.code);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(code);
        }
    }

    static final class TimedKey {
        private final String code;
        private final LongSupplier currentMillis;

        TimedKey(String code, LongSupplier currentMillis) {
            this.code = code;
            this.currentMillis = currentMillis;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof TimedKey that)) {
                return false;
            }
            return Objects.equals(code, that.code)
                    && currentMillis.getAsLong() < 1_000
                    && that.currentMillis.getAsLong() < 1_000;
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(code);
        }
    }

    public static void main(String[] args) {
        StableKey first = new StableKey("acme", 42);
        StableKey second = new StableKey("acme", 42);
        System.out.println("stable #1: " + first.equals(second));
        System.out.println("stable #2: " + first.equals(second));
        System.out.println("stable hash matches: "
                + (first.hashCode() == second.hashCode()));

        CountingKey counted = new CountingKey("A");
        System.out.println("count before: " + counted.comparisonCount());
        System.out.println("counted.equals(counted): "
                + counted.equals(counted));
        System.out.println("count after: " + counted.comparisonCount());

        AtomicLong fakeMillis = new AtomicLong(500);
        TimedKey left = new TimedKey("K", fakeMillis::get);
        TimedKey right = new TimedKey("K", fakeMillis::get);

        System.out.println("timed at 500: " + left.equals(right));

        Map<TimedKey, String> map = new HashMap<>();
        map.put(left, "found");
        System.out.println("map lookup at 500: " + map.get(right));

        fakeMillis.set(1_500);
        System.out.println("timed at 1500: " + left.equals(right));
        System.out.println("map lookup at 1500: " + map.get(right));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac --release 17 EqualsPurityDemo.java
java EqualsPurityDemo
```

Kết quả tiêu chuẩn (không phụ thuộc thời gian thực vì đã dùng đồng hồ giả):

```text
stable #1: true
stable #2: true
stable hash matches: true
count before: 0
counted.equals(counted): true
count after: 1
timed at 500: true
map lookup at 500: found
timed at 1500: false
map lookup at 1500: null
```

Diễn giải:

1. Hai `StableKey` có cùng `tenant` và `id` cho kết quả `true` ổn định. `hashCode` cũng dựa trên chính các trường này, đảm bảo các đối tượng được xem là bằng nhau có cùng mã băm.
2. `CountingKey.equals(counted)` trả `true` (tính phản xạ vẫn đúng) nhưng tăng `comparisons` từ `0` lên `1`. Như vậy **việc trả kết quả đúng chưa đồng nghĩa phương thức không có side effect**.
3. `TimedKey` so sánh cả `code` và điều kiện `currentMillis < 1_000`. Khi đồng hồ giả chuyển từ `500` sang `1_500` mà hai đối tượng không bị sửa trường nào, `left.equals(right)` đổi từ `true` thành `false`.
4. Trong ví dụ này `HashMap` được thêm `left` làm khóa và dùng `right` để tra cứu. Lúc `500`, `right` được coi bằng `left` nên tìm thấy giá trị; lúc `1_500`, nó không còn được coi bằng nữa nên kết quả là `null`. Mã băm ở đây vẫn như cũ; **chính quan hệ bình đẳng thay đổi theo đồng hồ** dẫn đến kết quả lookup đổi khác.
5. `left.equals(left)` vẫn `true` nhờ nhánh `this == other`: ví dụ thời gian này giữ tính phản xạ nhưng lại cho thấy một rủi ro **khác**, là kết quả so sánh giữa hai đối tượng thay đổi theo thời điểm. Không được đánh đồng việc qua một điều khoản với việc thiết kế `equals` đã đáng tin cậy.

`TimedKey` và `CountingKey` chỉ để chứng minh các cách làm cần tránh, không phải những cài đặt được khuyến nghị trong mã ứng dụng.

## 5. Ảnh hưởng đến `HashMap`, `HashSet` và các API khác

Một `HashMap` dùng `hashCode` để chọn nhóm băm và `equals` để xác định khóa tương đương khi cần. `HashSet` dựa trên ý tưởng tương tự. Nếu `equals` phụ thuộc trạng thái thay đổi, có thể xảy ra:

- Thêm một khóa rồi không tìm thấy khóa tương đương dù không hề chủ động xóa entry.
- `contains`, `get`, `remove` cho kết quả bất ngờ vào những thời điểm khác nhau.
- Phép đọc bị gắn với side effect: một lần so sánh có thể thay đổi dữ liệu mà các phép tra cứu sau sử dụng.

Cần phân biệt **ổn định của `equals`** với **ổn định của `hashCode`**. Hai phương thức phải thống nhất: khi `a.equals(b)` là `true`, `a.hashCode() == b.hashCode()` cũng phải là `true`. Nhưng chỉ có `hashCode` ổn định vẫn không cứu được một `equals` phụ thuộc đồng hồ, như ví dụ `TimedKey`.

Đối với khóa của `HashMap`/`HashSet`, thực tế tốt nhất là dùng thuộc tính định danh **bất biến** và dùng cùng tiêu chí trong `equals`/`hashCode`. Với đối tượng có dữ liệu mutable, hãy cẩn trọng khi đưa các trường có thể đổi vào bình đẳng, nhất là sau khi đối tượng đã được dùng làm khóa.

## 6. Thiết kế đúng: tách bình đẳng khỏi trạng thái vận hành

Một lớp lưu token và thời điểm hết hạn có thể cần cả khái niệm “cùng token” lẫn “token còn hiệu lực”. Hai câu hỏi này nên có API riêng.

Ví dụ **đoạn mã minh họa** Java 17 (các khai báo `import` phải được thêm khi đặt vào tệp độc lập):

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

final class SessionToken {
    private final String tokenId;
    private final Instant expiresAt;

    SessionToken(String tokenId, Instant expiresAt) {
        this.tokenId = Objects.requireNonNull(tokenId);
        this.expiresAt = Objects.requireNonNull(expiresAt);
    }

    boolean isExpired(Clock clock) {
        return !Instant.now(clock).isBefore(expiresAt);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof SessionToken that)) {
            return false;
        }
        return tokenId.equals(that.tokenId);
    }

    @Override
    public int hashCode() {
        return tokenId.hashCode();
    }
}
```

Ở mô hình ví dụ này, **bình đẳng được định nghĩa theo `tokenId`**; `expiresAt` không thuộc danh tính nên không xuất hiện trong `equals`/`hashCode`. Đây là lựa chọn nghiệp vụ cho ví dụ, không phải quy tắc bắt buộc cho mọi token. Nếu nghiệp vụ định nghĩa hai giá trị token khác nhau khi `expiresAt` khác nhau, có thể đưa **giá trị `expiresAt` đã lưu** vào cả `equals` và `hashCode`, miễn là chúng ổn định; vẫn không gọi đồng hồ hiện tại trong `equals`.

Phương thức `isExpired(Clock clock)` nhận nguồn thời gian tường minh, dễ kiểm thử với `Clock.fixed(...)`. Thời điểm hiệu lực có thể thay đổi theo thời gian, đúng với trách nhiệm của phương thức này; thay đổi đó không âm thầm thay đổi quan hệ bình đẳng của khóa.

Một lựa chọn khác cho đối tượng giá trị chỉ chứa dữ liệu bất biến là **Java record**:

```java
record CustomerKey(String tenantId, long customerId) {}
```

Java sinh `equals`/`hashCode` dựa trên các thành phần record. Ví dụ này phù hợp vì `String` và `long` ổn định. Tuy nhiên, **record không biến mọi thành phần tham chiếu thành bất biến sâu**: nếu chứa một mảng hoặc đối tượng mutable, vẫn phải xem lại ngữ nghĩa bình đẳng và mức độ ổn định của dữ liệu.

## 7. Những lỗi tinh vi cần tránh

### 7.1. Tự động chuẩn hóa dữ liệu bằng cách gán trường trong `equals`

Cách sai: khi so sánh tên, gọi setter để đổi `name` thành chữ thường hoặc trim ngay trên đối tượng. Điều đó làm `equals` biến thành một thao tác sửa dữ liệu; nếu trường được dùng trong `hashCode`, mã băm cũng có thể thay đổi.

Cách tốt hơn: chuẩn hóa ở constructor hoặc tại biên nhập dữ liệu, hoặc so sánh bằng kết quả chuẩn hóa cục bộ mà không ghi lại vào trường. Nếu chuẩn hóa theo locale, chọn quy tắc rõ ràng phù hợp nghiệp vụ; đừng dùng locale mặc định toàn cục biến đổi mà không chủ đích.

### 7.2. Lazy initialization làm thay đổi các trường tham gia bình đẳng

Ví dụ `equals` gọi một getter lười khởi tạo bằng cách cập nhật ID hay timestamp. Lần so sánh đầu tiên có thể ảnh hưởng đến lần sau. Nên xác lập danh tính trước khi dùng trong so sánh và bảo đảm đọc giá trị không tự đổi ý nghĩa của danh tính.

Không phải mọi cache nội bộ đều đương nhiên phá hợp đồng, nhưng nó làm tăng độ khó về side effect và thread safety. Với kiến thức nền tảng, hãy ưu tiên phép so sánh thuần chỉ đọc.

### 7.3. Phụ thuộc giá trị bên ngoài: random, cấu hình, database

Không lấy kết quả `Random.nextBoolean()`, phiên bản cấu hình, mạng, quyền truy cập hiện hành hoặc kết quả truy vấn database để quyết định hai đối tượng đã được tạo có bằng nhau không. Những nguồn đó có thể thay đổi giữa hai lần gọi và làm cho một phép kiểm tra giá trị mang tính trạng thái vận hành.

### 7.4. Mutable field trong đối tượng đang dùng làm khóa

Nếu `equals`/`hashCode` dựa trên trường có thể thay đổi, sau khi đặt đối tượng vào `HashMap`, việc sửa trường có thể khiến lookup thất bại. Đây là vấn đề ngay cả khi `equals` **không tự sửa** trường đó. Vì vậy cần xem xét cả **side effect của phương thức** và **tính bất biến của các thuộc tính được dùng trong so sánh**.

### 7.5. Đồng thời (concurrency)

Một cài đặt `equals` đọc nhiều trường mutable trong khi thread khác sửa có thể quan sát một tổ hợp dữ liệu không nhất quán. Khai báo `final` và thiết kế value object bất biến giúp đơn giản hóa. Nếu đối tượng thực sự phải mutable, cần chiến lược đồng bộ/snapshot thích hợp cho yêu cầu nghiệp vụ; chỉ thêm `volatile` cho từng trường không tự động cung cấp ảnh chụp nhất quán của nhiều trường.

## 8. Kiểm tra khi review và test

Với cùng hai đối tượng có dữ liệu cần so sánh không đổi, có thể kiểm thử:

1. Gọi `a.equals(b)` nhiều lần và so kết quả; đồng thời kiểm tra `a.equals(a)`, `a.equals(null)` cùng các điều khoản bình đẳng liên quan.
2. Chụp trạng thái có thể quan sát của `a` và `b` trước/sau phép gọi; bảo đảm không có trường nào bị sửa ngoài chủ đích. Đặc biệt chú ý tới phương thức getter có lazy write.
3. Khi thiết kế có `Clock`, fake clock hoặc test time boundary, thay đổi thời gian nhưng **giữ nguyên dữ liệu danh tính**; kết quả `equals` không nên đổi.
4. Nếu lớp dùng làm khóa, thử `HashMap.put` rồi `get` bằng một đối tượng tương đương; chạy lại sau những thao tác không được phép làm thay đổi danh tính.
5. Kiểm tra `hashCode` luôn phù hợp với các trường `equals` sử dụng, và dữ liệu khóa không đổi khi đang nằm trong cấu trúc băm.

Lưu ý: test vài giá trị mẫu không chứng minh tuyệt đối mọi tính chất. Cần đọc cả đường đi của code để phát hiện việc ghi trạng thái, gọi đồng hồ hoặc phụ thuộc dịch vụ bên ngoài.

## 9. Tổng kết kiến thức cần nhớ

- `equals` nên là thao tác **chỉ đọc và có kết quả dễ dự đoán**; không sửa chính đối tượng, đối tượng đối diện hay trạng thái hệ thống.
- Theo hợp đồng `Object.equals`, các lần so sánh lặp lại phải nhất quán **khi thông tin dùng cho so sánh không đổi**.
- Không dùng `Instant.now()`, `System.currentTimeMillis()`, random, số lần gọi hoặc trạng thái dịch vụ bên ngoài để quyết định bình đẳng.
- “Hai giá trị có cùng danh tính hay không?” và “Giá trị đó còn hiệu lực tại thời điểm này không?” là **hai trách nhiệm khác nhau**; hãy tách `equals` và phương thức kiểm tra thời gian.
- Dùng trường danh tính ổn định, và giữ tiêu chí `equals`/`hashCode` thống nhất, nhất là với khóa trong `HashMap`/`HashSet`.
