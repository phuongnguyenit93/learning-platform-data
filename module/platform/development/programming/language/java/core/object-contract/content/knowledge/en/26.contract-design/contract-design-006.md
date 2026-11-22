# Đánh giá ảnh hưởng khi thêm trường hoặc thay đổi phiên bản lớp

## 1. Vì sao đây là thay đổi hợp đồng, không chỉ là thay đổi cấu trúc?

Trong Java, một lớp là tập hợp nhiều **hợp đồng quan sát được**: dữ liệu và phương thức công khai, cách xác định hai đối tượng bằng nhau, cách tạo mã băm, cách sắp xếp, cách biểu diễn thành chuỗi và đôi khi cách lưu/truyền dữ liệu. Thêm trường hoặc phát hành phiên bản lớp mới có thể tác động đến từng hợp đồng với mức độ khác nhau.

Ví dụ, một đối tượng tài khoản có `accountId` và `displayName`. Nếu thêm `membershipTier`, cần trả lời: hai đối tượng cùng `accountId` nhưng khác `membershipTier` còn được xem là cùng tài khoản hay không? Nếu câu trả lời là **có**, trường mới là thuộc tính mô tả và không nên tự động tham gia phép so sánh định danh logic. Nếu câu trả lời là **không**, việc đưa trường mới vào `equals()` là thay đổi **ngữ nghĩa bằng nhau**; mọi mã phụ thuộc vào tập hợp, bản đồ, cache hoặc dữ liệu cũ có thể bị ảnh hưởng.

Phân biệt các loại thay đổi:

- **Thay đổi cấu trúc:** thêm, xóa, đổi tên, đổi kiểu hoặc đổi tính mutable của trường; thêm component của `record`.
- **Thay đổi API:** đổi constructor, accessor, method, thứ tự tham số hoặc khả năng truy cập.
- **Thay đổi ngữ nghĩa:** thay đổi điều kiện `equals()`, `hashCode()`, `compareTo()`, comparator hoặc thông tin trong `toString()`.
- **Thay đổi tương thích dữ liệu:** bản mới đọc dữ liệu do bản cũ ghi thế nào và ngược lại; thay đổi Java serialization, JSON, schema database hoặc cấu trúc cache.

Một thay đổi có thể giữ chương trình **biên dịch được** nhưng vẫn làm hành vi nghiệp vụ sai. Do đó, đánh giá hợp đồng cần xét cả mã nguồn, chương trình đã biên dịch, trạng thái runtime và dữ liệu lưu trữ.

## 2. Các bất biến cần giữ khi thay đổi `equals()` và `hashCode()`

Với đối tượng không null, `equals` phải tuân theo hợp đồng cơ bản của Java:

1. **Phản xạ:** `x.equals(x)` là `true`.
2. **Đối xứng:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
3. **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` đều đúng, `x.equals(z)` phải đúng.
4. **Nhất quán:** kết quả không tự đổi khi thông tin dùng để so sánh không thay đổi.
5. **Với null:** `x.equals(null)` trả `false`.

`hashCode()` phải nhất quán với `equals()`:

- Nếu `a.equals(b)` đúng, `a.hashCode() == b.hashCode()` phải đúng.
- Hai đối tượng **không bằng nhau** vẫn có thể trùng hash code; mã băm không phải định danh duy nhất.
- Trong phạm vi một lần chạy và khi thông tin dùng cho `equals` không đổi, mã băm phải ổn định theo hợp đồng.
- Không có yêu cầu hash code của một object phải giữ nguyên giữa các lần chạy Java khác nhau.

**Điểm kiểm tra khi thêm trường:** nếu trường mới tham gia `equals`, hãy cập nhật `hashCode` theo **cùng tập thông tin tương đương**. Ngược lại, thêm trường chỉ để hiển thị thường không cần thay `equals` và `hashCode`.

| Cách xử lý trường mới | Ảnh hưởng tới phép bằng nhau | Hệ quả đáng kiểm tra |
| --- | --- | --- |
| Không đưa vào `equals`/`hashCode` | Đối tượng cũ và mới vẫn có thể bằng nhau theo khóa đã xác định | Không bỏ qua trường nếu nghiệp vụ thực sự yêu cầu phân biệt |
| Đưa vào cả hai | Hai đối tượng trước đây bằng nhau có thể thành khác nhau | `HashMap`, `HashSet`, cache key, deduplication, kiểm thử và migration |
| Đưa vào `equals` nhưng quên `hashCode` | Có nguy cơ vi phạm hợp đồng khi hai đối tượng bằng nhau có hash code khác | Lookup/số lượng phần tử trong cấu trúc băm sai hoặc khó đoán |
| Đưa vào `hashCode` nhưng bỏ khỏi `equals` | Có thể trực tiếp vi phạm quy tắc hai đối tượng bằng nhau có cùng hash code | Tra cứu khóa bằng đối tượng tương đương thất bại |

Quyết định đưa trường vào phép so sánh phải xuất phát từ **định nghĩa cùng một giá trị/cùng một thực thể logic** của miền nghiệp vụ, không chỉ từ việc lớp vừa có thêm một biến thành viên.

## 3. Ví dụ: thêm thuộc tính nhưng giữ nguyên định danh logic

Một hệ thống dùng `accountId` làm khóa logic. `displayName` và `tier` có thể thay đổi mà vẫn là cùng một tài khoản. Nếu các thuộc tính này chỉ mô tả tài khoản, chúng không nên làm hai bản biểu diễn cùng ID thành hai khóa khác nhau.

Tạo file **`AccountContractDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class AccountContractDemo {
    static final class Account {
        private final String accountId;
        private final String displayName;
        private final String tier;

        Account(String accountId, String displayName, String tier) {
            this.accountId = Objects.requireNonNull(accountId);
            this.displayName = Objects.requireNonNull(displayName);
            this.tier = Objects.requireNonNull(tier);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Account that)) return false;
            return accountId.equals(that.accountId);
        }

        @Override
        public int hashCode() {
            return accountId.hashCode();
        }

        @Override
        public String toString() {
            return "Account[id=" + accountId
                    + ", name=" + displayName
                    + ", tier=" + tier + "]";
        }
    }

    public static void main(String[] args) {
        Account before = new Account("A-07", "Lan", "BASIC");
        Account after = new Account("A-07", "Lan Nguyen", "GOLD");

        System.out.println("same instance: " + (before == after));
        System.out.println("equal by accountId: " + before.equals(after));
        System.out.println("same hash: " + (before.hashCode() == after.hashCode()));

        Map<Account, String> statusByAccount = new HashMap<>();
        statusByAccount.put(before, "ACTIVE");
        System.out.println("status via updated view: "
                + statusByAccount.get(after));
        System.out.println("map size: " + statusByAccount.size());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac AccountContractDemo.java
java AccountContractDemo
```

Kết quả:

```text
same instance: false
equal by accountId: true
same hash: true
status via updated view: ACTIVE
map size: 1
```

Hai lần `new Account(...)` tạo ra **hai instance khác nhau**, nhưng cả hai đại diện cùng khóa logic `A-07`. `HashMap` vẫn tra được giá trị vì `equals` và `hashCode` cùng dựa trên `accountId`.

Ví dụ này chỉ đúng khi miền nghiệp vụ bảo đảm rằng **một `accountId` không tái sử dụng để chỉ tài khoản khác** trong cùng phạm vi cần so sánh. Nếu khóa logic thực tế gồm cả `tenantId` và `accountId`, cả hai phải tham gia `equals` và `hashCode`. Nếu thêm `tenantId` để khắc phục ID trùng giữa các tenant, đó là thay đổi hợp đồng **có chủ đích** và cần kế hoạch chuyển dữ liệu.

## 4. Ví dụ phản chứng: sửa trường dùng làm khóa sau khi đã đưa vào `HashMap`

Với một khóa mà `hashCode` dựa trên trường có thể đổi, sửa giá trị sau khi thêm vào map có thể làm entry trở nên không thể tra cứu theo khóa đó. Đây là rủi ro đặc biệt lớn nếu phiên bản mới chuyển từ so sánh theo ID bất biến sang so sánh thêm trường mutable.

Tạo file **`MutableKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class MutableKeyDemo {
    static final class Key {
        String id;

        Key(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Key that && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        Map<Key, String> map = new HashMap<>();
        Key key = new Key("A");

        map.put(key, "stored");
        System.out.println("before mutation: " + map.get(key));

        key.id = "B";
        System.out.println("after mutation: " + map.get(key));
        System.out.println("map size: " + map.size());
    }
}
```

Chạy:

```bash
javac MutableKeyDemo.java
java MutableKeyDemo
```

Kết quả:

```text
before mutation: stored
after mutation: null
map size: 1
```

Entry vẫn tồn tại trong map nhưng phép tra cứu dùng mã băm mới `"B".hashCode()` nên không tìm được entry đặt dưới hash của `"A"`. Không thể chữa gốc lỗi bằng cách chỉ viết lại `hashCode()`: thông tin tham gia khóa phải **ổn định trong thời gian khóa nằm trong collection**. Ưu tiên khóa immutable hoặc xóa entry trước khi thay giá trị và thêm lại theo khóa mới khi có yêu cầu nghiệp vụ rõ ràng.

Ngay cả lớp có các trường `final` vẫn cần xét **tính bất biến sâu**: tham chiếu `final List<String> tags` không thể bị gán lại, nhưng nội dung list vẫn có thể thay đổi. Nếu đưa list mutable vào `equals`/`hashCode`, có rủi ro tương tự. Sao chép phòng vệ và giữ component bất biến khi cần.

## 5. Bảng ảnh hưởng theo kiểu thay đổi lớp

| Thay đổi | Rủi ro hợp đồng | Việc cần kiểm tra |
| --- | --- | --- |
| Thêm trường mô tả không tham gia equality | Thường giữ được value equality hiện tại; `toString` hoặc JSON có thể đổi | Output, logging, serialization, schema |
| Thêm trường tham gia equality | Các đối tượng trước đây bằng nhau có thể không bằng nhau | `equals`/`hashCode`, collection, key và dữ liệu cũ |
| Đổi tên trường nhưng giữ nguyên ý nghĩa | Có thể không đổi equality nhưng đứt tên field/API/serialization | Accessor, constructor, JSON property, database column |
| Đổi kiểu trường, ví dụ `int` sang `long` | Có thể đổi API/bytecode descriptor; coercion và equality | Nguồn gọi, binary linkage, chuyển dữ liệu, giá trị biên |
| Xóa trường | API và dữ liệu cũ có thể cần trường đã bị xóa | Constructor, getter, dữ liệu lưu, ứng dụng cũ |
| Biến trường immutable thành mutable | Rủi ro hash key bị thay đổi trong khi đang được sử dụng | `HashMap`/`HashSet`, race condition, defensive copy |
| Thêm component vào `record` | Equality, hash, chuỗi biểu diễn và canonical constructor thay đổi mặc định | Caller, các so sánh, serialization |
| Đổi lớp cha hoặc cách xét type | Có thể gây lỗi đối xứng/bắc cầu ở `equals` | Test giữa base/subclass, quy tắc kế thừa |
| Đổi comparator hoặc `compareTo` | `TreeSet`/`TreeMap` có thể coi hai khóa là cùng phần tử theo ordering | Tính nhất quán với `equals` và thứ tự nghiệp vụ |
| Đổi `toString` | Mã tích hợp nào parse chuỗi có thể hỏng; log có thể lộ dữ liệu | Không xem `toString` là API máy đọc; kiểm tra dữ liệu nhạy cảm |

Một **trường mới không tự động đòi hỏi đưa vào mọi phương thức**. Hợp đồng từng phương thức được thiết kế độc lập: khóa logic cho equality; thứ tự nghiệp vụ cho ordering; biểu diễn dễ quan sát, không rò rỉ thông tin cho `toString`.

## 6. Lưu ý đặc biệt với `record` và mã được sinh

Với `record`, Java sinh sẵn `equals`, `hashCode` và `toString` dựa trên các record component nếu không được ghi đè. Thêm một component có thể làm thay đổi quan hệ bằng nhau ngay cả khi nhà phát triển **không sửa trực tiếp phương thức `equals`**.

Ví dụ minh họa hai hình dạng dữ liệu trước và sau khi thêm component; tạo file **`RecordEvolutionDemo.java`**:

```java
public class RecordEvolutionDemo {
    record InvoiceV1(String invoiceId) {}
    record InvoiceV2(String invoiceId, String label) {}

    public static void main(String[] args) {
        InvoiceV1 oldA = new InvoiceV1("I-1");
        InvoiceV1 oldB = new InvoiceV1("I-1");

        InvoiceV2 newA = new InvoiceV2("I-1", "draft");
        InvoiceV2 newB = new InvoiceV2("I-1", "paid");

        System.out.println("V1 equal: " + oldA.equals(oldB));
        System.out.println("V2 equal: " + newA.equals(newB));
        System.out.println("V1 text: " + oldA);
        System.out.println("V2 text: " + newA);
    }
}
```

Chạy:

```bash
javac RecordEvolutionDemo.java
java RecordEvolutionDemo
```

Kết quả:

```text
V1 equal: true
V2 equal: false
V1 text: InvoiceV1[invoiceId=I-1]
V2 text: InvoiceV2[invoiceId=I-1, label=draft]
```

Trong mã thực, việc đổi từ `record Invoice(String invoiceId)` sang `record Invoice(String invoiceId, String label)` còn thay đổi **canonical constructor**: lời gọi `new Invoice("I-1")` cũ không còn hợp lệ ở cấp mã nguồn trừ khi nhà phát triển chủ động cung cấp constructor tương thích. Các class đã biên dịch có thể gặp lỗi liên kết nếu constructor mà chúng gọi không còn tồn tại.

Hai kiểu `InvoiceV1` và `InvoiceV2` ở ví dụ chỉ minh họa **sự thay đổi về cấu trúc và kết quả**, không phải là bằng chứng rằng có thể so sánh trực tiếp object thuộc hai kiểu như cùng một lớp qua hai lần triển khai. Với Java record, cũng không thể dựa vào khả năng kế thừa từ một record để chia sẻ equality giữa các phiên bản: record là final.

Nếu ý nghĩa equality phải chỉ theo `invoiceId`, có thể cân nhắc ghi đè `equals` và `hashCode` một cách nhất quán, hoặc tốt hơn là tách **kiểu khóa nghiệp vụ ổn định** (chẳng hạn `InvoiceId`) khỏi record mang dữ liệu nhiều phiên bản. Không thay đổi tùy tiện equality của record chỉ vì muốn bỏ qua một khác biệt đang cần phân biệt trong nghiệp vụ.

## 7. Tương thích nguồn, nhị phân, hành vi và dữ liệu là bốn câu hỏi riêng

### 7.1. Source compatibility: mã nguồn của caller cũ còn biên dịch?

Xét các trường hợp:

- Thêm trường `private` kèm constructor cũ vẫn tồn tại có thể ít ảnh hưởng tới caller.
- Thêm tham số bắt buộc vào constructor và **loại bỏ constructor cũ** làm lời gọi trước đây không còn biên dịch.
- Thay tên getter, thay tên field `public` hoặc thay kiểu trả về có thể làm caller không biên dịch.
- Thêm component vào record làm thay đổi canonical constructor và thêm accessor mới; constructor cũ chỉ còn nếu được cung cấp tương thích.
- Đổi generic signature có thể gây lỗi compile tại caller dù JVM type erasure tạo ra một số tình huống đặc biệt; cần kiểm tra thực tế theo API được xuất bản.

### 7.2. Binary compatibility: bytecode đã biên dịch còn chạy?

Các module hoặc thư viện triển khai độc lập có thể đang dùng file `.class` được biên dịch trước đó. Nếu xóa/đổi descriptor của field, method, constructor mà bytecode gọi, runtime có thể phát sinh lỗi như `NoSuchFieldError`, `NoSuchMethodError` hoặc `IllegalAccessError` khi liên kết/truy cập.

Một thay đổi có thể **binary-compatible** nhưng **behavior-incompatible**: ví dụ API vẫn nguyên, song `equals` nay so thêm `tier` khiến số lượng phần tử trong `HashSet` tăng ngoài dự kiến. Đánh giá binary compatibility không đủ để đảm bảo hợp đồng đối tượng.

### 7.3. Behavioral compatibility: kết quả sử dụng object có còn như trước?

Đặc biệt cần kiểm tra:

- Kết quả `equals` của hai bản biểu diễn cùng thực thể.
- Giá trị `hashCode` phù hợp với equality trong cùng phiên bản.
- Số lượng phần tử của `HashSet`, `TreeSet` và key trùng của `HashMap`, `TreeMap`.
- Dedupe, cache key, memoization, grouping, batching và idempotency logic dựa vào equality.
- So sánh giữa lớp cha và lớp con, cũng như qua các proxy/kiểu phát sinh từ framework.
- Log và `toString` nếu đã bị bên ngoài vô tình sử dụng như định dạng dữ liệu.

### 7.4. Data compatibility: bản mới và bản cũ có đọc được dữ liệu của nhau?

Cần xét dữ liệu thực tế: Java object serialization (nếu dùng), JSON/XML, cache, database, event/message và snapshot. “Đã thêm một field” không tự trả lời được liệu dữ liệu **cũ thiếu field** có dùng được hay liệu consumer **cũ gặp field lạ** có chấp nhận hay không; điều này tùy thư viện, cấu hình, schema và chính sách xử lý mặc định.

Làm rõ **hai chiều** tương thích:

| Chiều | Câu hỏi |
| --- | --- |
| New reader ← Old data | Khi trường mới vắng mặt, có default/backfill/migration hợp lệ không? |
| Old reader ← New data | Consumer cũ chấp nhận trường mới hay sẽ báo lỗi? |
| Old service ↔ New service | Trong lúc rolling deployment, message và khóa logic có ổn định không? |
| Persistence/cache | Dữ liệu/khóa phiên bản trước có thể bị đọc sai, miss hoặc tạo bản trùng không? |

Nếu equality/hash code tham gia khóa cache hoặc định dạng ID lưu lâu dài, phải xem xét migration hoặc version của key. `hashCode` của Java **không** phù hợp để lưu làm định danh bền vững giữa các phiên bản hay JVM.

## 8. Java serialization: xử lý riêng nếu lớp triển khai `Serializable`

Java native serialization lưu thông tin dạng object stream và áp dụng quy tắc tương thích phiên bản lớp. Một số điểm quan trọng:

- `serialVersionUID` dùng để kiểm tra tương thích phiên bản serialization của các lớp serializable thông thường. Nếu UID nhận từ stream khác UID của lớp cục bộ và quy tắc kiểm tra áp dụng, deserialization có thể ném `InvalidClassException`.
- Khi không khai báo `serialVersionUID`, JVM tính giá trị mặc định dựa trên cấu trúc lớp; các thay đổi lớp có thể làm giá trị này thay đổi ngoài ý muốn. Nếu có yêu cầu tương thích, khai báo UID rõ ràng ngay từ đầu và kiểm thử với dữ liệu cũ.
- Với **thay đổi tương thích** và UID phù hợp, stream cũ không có field mới có thể được đọc với giá trị mặc định Java của field mới: `null`, `0`, `false`, v.v. Đây chưa chắc là giá trị **hợp lệ về nghiệp vụ**.
- Tương thích serialization **không** đồng nghĩa tương thích equality: object khôi phục có trường mới bằng `null` có thể cho kết quả `equals`/`hashCode` khác và có thể khiến mã xử lý bị `NullPointerException`.
- Đổi kiểu, cấu trúc kế thừa, kiểu đối tượng hay các cơ chế serializing có những ràng buộc riêng; chỉ giữ nguyên UID không biến mọi thay đổi thành tương thích.
- Java record có cơ chế serialization đặc thù, gồm việc dựng lại bằng canonical constructor; không suy diễn máy móc các quy tắc `serialVersionUID` của lớp thông thường sang record.

Ví dụ về ý tưởng, **không phải hai phiên bản cùng chạy trong một file**:

```java
// Phiên bản cũ:
class Profile implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    String id;
}

// Phiên bản mới, cùng tên binary của lớp khi được thay thế trong ứng dụng:
class Profile implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    String id;
    String region; // dữ liệu cũ có thể đọc ra null trong trường hợp tương thích
}
```

Đây là hai **bản phác thảo phiên bản tách biệt** nên không được biên dịch đồng thời dưới cùng tên lớp. Một cách kiểm thử có giá trị là dùng phiên bản cũ ghi ra file fixture, dùng phiên bản mới đọc fixture ấy, rồi kiểm tra giá trị mặc định, bất biến của đối tượng và equality. Làm thêm chiều ngược lại khi hệ thống cần hỗ trợ consumer cũ. Native Java serialization không được khuyến nghị làm định dạng trao đổi dữ liệu mới giữa những dịch vụ không tin cậy; cân nhắc định dạng có schema và chính sách tương thích rõ ràng.

## 9. Hợp đồng sắp xếp: `compareTo()` và `Comparator`

Thêm trường có thể làm thứ tự hiển thị thay đổi. Đây là vấn đề riêng với equality. Chẳng hạn trước đây sản phẩm sắp theo `sku`, sau đó theo `category` rồi `sku`. Nếu comparator dùng trong `TreeSet` hoặc `TreeMap`, hai khóa được coi là tương đương khi `compare(a, b) == 0`; cấu trúc cây dùng kết quả so sánh thứ tự để xác định tính trùng khóa.

Một ví dụ bất nhất: `equals` so `sku` **và** `revision`, nhưng comparator chỉ so `sku`. Hai đối tượng có cùng SKU và khác revision không `equals` nhau, nhưng `TreeSet` dùng comparator ấy chỉ giữ một phần tử cho cùng SKU. Java khuyến nghị natural ordering của `Comparable` nhất quán với `equals` để tuân hợp đồng `Set`/`Map` dễ dự đoán; comparator cố ý khác phải được tài liệu hóa và kiểm tra theo mục đích.

Để giữ ổn định:

1. Quy định rõ trường nào quyết định **bằng nhau** và trường nào quyết định **thứ tự**.
2. Với `TreeSet`/`TreeMap`, kiểm tra tác động khi `compareTo` hoặc comparator coi các object khác nhau là cùng khóa.
3. Nếu cần thứ tự hiển thị riêng, dùng comparator khi sort một collection phù hợp, thay vì mặc nhiên dùng nó làm định nghĩa uniqueness.
4. Nếu trường dùng để sắp xếp là mutable, thay đổi nó khi object đang nằm trong cấu trúc cây có thể làm bất biến thứ tự nội bộ bị phá vỡ; remove–update–reinsert hoặc dùng khóa immutable.

## 10. Kế thừa và thay đổi kiểu: tránh phá tính đối xứng

Một lớp cha có `equals` cho phép `instanceof Base`, nhưng lớp con lại thêm một trường vào equality, có thể gây ra tình huống `base.equals(child)` đúng trong khi `child.equals(base)` sai. Đây là vi phạm **đối xứng**.

Ví dụ về **mẫu thiết kế nguy hiểm** (minh họa, không khuyến nghị dùng làm ứng dụng):

```java
class Base {
    final String id;

    Base(String id) { this.id = id; }

    @Override
    public boolean equals(Object o) {
        return o instanceof Base that && id.equals(that.id);
    }

    @Override
    public int hashCode() { return id.hashCode(); }
}

class Child extends Base {
    final String zone;

    Child(String id, String zone) {
        super(id);
        this.zone = zone;
    }

    @Override
    public boolean equals(Object o) {
        return o instanceof Child that
                && id.equals(that.id)
                && zone.equals(that.zone);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(id, zone);
    }
}
```

Với `Base b = new Base("X"); Child c = new Child("X", "north");`, biểu thức `b.equals(c)` là `true`, còn `c.equals(b)` là `false`. Tình huống này thường xuất hiện khi phiên bản mới mở rộng hệ phân cấp và quyết định đưa thông tin bổ sung của subtype vào so sánh.

Biện pháp thường dùng: thiết kế value type bất biến và `final` khi phù hợp; quy định chặt chẽ cách so sánh giữa các subtype; hoặc tránh inheritance cho value equality phức tạp và dùng composition. So sánh bằng `getClass()` có thể giữ ranh giới kiểu nghiêm ngặt hơn nhưng cũng có đánh đổi khi cần hỗ trợ proxy/subtype từ framework. Không đổi chiến lược equality toàn bộ hierarchy chỉ để xử lý một trường mới.

## 11. Đánh giá ảnh hưởng tới API, cache, dữ liệu và hệ phân tán

Một lần thay đổi class nên đi theo đường phụ thuộc thực tế:

```text
Field / constructor / record component thay đổi
              |
              +--> equals / hashCode ----> HashMap, HashSet, cache, dedupe
              |
              +--> compareTo / Comparator -> TreeMap, TreeSet, sắp xếp
              |
              +--> toString -------------> logs, diagnostics, biểu diễn
              |
              +--> public API -----------> source/binary callers
              |
              +--> serialization --------> file, JSON, event, DB, cache
```

Ví dụ hệ thống lưu cache theo một object key với `equals` dựa trên `customerId`. Phiên bản mới bổ sung `country` vào equality. Trong đợt triển khai đồng thời phiên bản cũ/mới:

- Khóa logic trước đây gom các bản cùng ID có thể phân mảnh theo quốc gia ở phiên bản mới.
- Cache hit rate và số entry có thể thay đổi, ảnh hưởng bộ nhớ, hiệu năng, kết quả dedupe.
- Nếu hệ thống dùng key string bền vững do ứng dụng xây dựng từ các trường, định dạng key cũng phải được version hoặc migration.
- Khi dữ liệu cũ thiếu `country`, cần quy tắc phân loại hợp lệ thay vì tự coi `null` là quốc gia thực.

Không trao đổi trực tiếp hash code do JVM tạo như một mã định danh cross-service. Nếu muốn định danh qua dịch vụ, dùng business ID có schema ổn định, hoặc xây dựng khóa định danh được quy định rõ (bao gồm namespace/tenant nếu cần).

## 12. Quy trình thay đổi lớp có kiểm soát

### Bước 1 — Ghi rõ tính chất của trường mới

Chọn một trong các vai trò (có thể có hơn một, cần chỉ ra cụ thể): khóa logic, thuộc tính giá trị, dữ liệu mô tả, trường hiển thị, trạng thái runtime, trường dẫn xuất, giá trị chỉ dùng cho phiên bản giao thức. Hỏi: “Hai object khác nhau chỉ ở trường này có cần được xem là cùng giá trị không?”

### Bước 2 — Liệt kê hợp đồng cần tác động

Kiểm tra `equals`, `hashCode`, `compareTo`/comparator, `toString`, constructor, accessor, serialization mapping, schema, cache key, validation và các ràng buộc của entity ORM. Với `record`, rà lại phương thức được compiler sinh. Với class dùng Lombok hoặc thư viện sinh mã, xem cấu hình include/exclude của các trường trong equality/toString và mã thực sự được sinh.

### Bước 3 — Xác định mức độ tương thích cần giữ

Phân loại rõ: source, binary, behavioral, data. Đọc yêu cầu rollout: có consumer biên dịch cũ, tiến trình chạy đồng thời nhiều phiên bản, dữ liệu cache cũ, file serialized cũ hoặc message còn tồn đọng không? Chỉ lựa chọn chiến lược tương thích cho các hướng thực sự cần hỗ trợ.

### Bước 4 — Chuẩn bị migration khi semantics thay đổi

Có thể cần chuyển sang khóa logic độc lập, áp default hợp lệ cho field mới, chuyển dữ liệu đã lưu, thay phiên bản cache key, làm mới index, hoặc triển khai thay đổi theo pha để cả producer và consumer hiểu cùng một schema trong giai đoạn chuyển tiếp. Các lựa chọn phụ thuộc hệ thống; **không** có thao tác tự động an toàn cho mọi lớp.

### Bước 5 — Test hợp đồng và hành vi tích hợp

Viết test với dữ liệu cả phiên bản cũ lẫn mới. Test nhất quán của equality/hash, phân biệt immutable và mutable key; đồng thời test tập hợp/map đã được sử dụng trong thực tế. Chạy compatibility fixture với schema/serialized data khi có persistence.

### Bước 6 — Tài liệu hóa và công bố thay đổi

Nếu public library/API thay đổi, ghi migration guide, release notes, default mới, thay đổi constructor, JSON field, hành vi equality. Tăng version theo chính sách phát hành của dự án; không giả định rằng chỉ tăng số phiên bản sẽ tự tạo tương thích.

## 13. Ma trận kiểm thử thực tế

| Trường hợp thử | Mục đích | Kết quả kỳ vọng |
| --- | --- | --- |
| `x.equals(x)`; `x.equals(null)` | Phản xạ/null | `true`; `false` |
| `x.equals(y)` và `y.equals(x)` | Đối xứng, kể cả base/subclass | Hai kết quả giống nhau |
| `x == y` nhưng bản sao dữ liệu độc lập | Phân biệt identity/value equality | Quyết định đúng theo contract đã định |
| `x.equals(y)` đúng | Hợp đồng hash | `x.hashCode() == y.hashCode()` |
| Chỉ đổi trường mô tả không tham gia equality | Ổn định khóa logic | `equals` không đổi, map vẫn tìm được |
| Đổi trường thật sự tham gia equality | Xác nhận semantics mới | Cặp object có thể từ bằng thành khác; test có chủ đích |
| Khóa mutable đã nằm trong map | Phát hiện rủi ro | Không cho phép sửa trực tiếp hoặc có chiến lược reinsert |
| Thay comparator/`compareTo` | Tương thích với uniqueness của cây | Không mất item sai yêu cầu |
| Deserialize old fixture bằng lớp mới | Dữ liệu cũ | Default/migration đúng; bất biến không bị phá |
| Đọc new data bằng old consumer | Rolling deployment | Thành công hoặc chủ động chặn theo chính sách |
| Biên dịch caller cũ và chạy binary cũ | API/bytecode | Không có lỗi biên dịch/liên kết ngoài phạm vi phá vỡ đã công bố |
| Ghi log từ `toString` | Dữ liệu bảo mật và quan sát | Không lộ token, mật khẩu, thông tin nhạy cảm |

Khi đổi equality, một bài test chỉ kiểm tra `equals` là chưa đủ: cần xác minh cách `HashMap` lấy lại cùng khóa, cách `HashSet` loại phần tử trùng và cách `TreeSet` xác định trùng theo comparator. Nếu ứng dụng dùng cache hay storage, test với dữ liệu thực tế của phiên bản trước quan trọng hơn chỉ tạo test object mới.

## 14. Những nhầm lẫn cần tránh

**“Thêm field thì IDE sinh lại `equals/hashCode` với tất cả field.”** Cách sinh mã tự động không thay bạn quyết định identity/value semantics. Nó có thể vô tình biến trường hiển thị, timestamp hay trường mutable thành thành phần khóa.

**“`serialVersionUID` giữ nguyên thì mọi phiên bản đều tương thích.”** UID không giải quyết mọi thay đổi kiểu/cấu trúc, bất biến nghiệp vụ hoặc thay đổi equality sau khi đọc dữ liệu.

**“Không đổi chữ ký phương thức nghĩa là không phá client.”** Client vẫn có thể sai vì `equals` thay đổi, comparator đổi thứ tự hoặc JSON representation khác.

**“Cùng hash code tức là cùng object/cùng giá trị.”** Có thể có va chạm; chỉ kết hợp `equals` theo hợp đồng thích hợp khi so sánh value equality. Với reference identity, dùng `==` và cấu trúc dữ liệu theo identity.

**“Mọi field trong record đều là business identity.”** Record mang tính giá trị với equality được sinh trên toàn bộ component theo mặc định; lựa chọn record component phải phù hợp semantics. Có thể tách object mô tả và value key khi không muốn mọi trường tham gia equality.

**“Tương thích hai chiều luôn cần thiết.”** Chỉ xây dựng những chiều cần theo sơ đồ deploy và vòng đời dữ liệu; nhưng phải xác định rõ trước khi phát hành. Trong rolling deployment, khả năng chạy đồng thời hai phiên bản thường quan trọng.

## 15. Bài tập tư duy

**Tình huống 1.** `User` có `id` bất biến và `displayName`. Phiên bản sau thêm `avatarUrl`. Mục tiêu: một ID là một người dùng duy nhất trong cache. Có nên tự động đưa `avatarUrl` vào `equals`/`hashCode`?

**Gợi ý:** Không, nếu business equality xác định theo ID. Trường mô tả có thể đổi thường xuyên; cần bảo đảm contract dùng đúng ID duy nhất trong phạm vi (ví dụ `tenantId + id`).

**Tình huống 2.** `record Price(String currency, long minorUnits)` được mở rộng thêm `taxCategory` và hệ thống bỗng giữ nhiều price key hơn trong `HashMap`. Điều gì phải kiểm tra trước?

**Gợi ý:** `record` sinh equality/hash từ các component; xác nhận `taxCategory` có thực sự làm hai giá trị giá khác nhau theo nghiệp vụ không. Nếu có, kết quả phân biệt là đúng và consumer/cache cần cập nhật; nếu không, thiết kế lại biểu diễn giá trị/khóa hoặc triển khai equality một cách có chủ đích.

**Tình huống 3.** Bản mới của một lớp `Serializable` thêm `region`. Đọc file của bản cũ cho `region == null`, sau đó `equals` gọi `region.equals(...)` và ném `NullPointerException`. Lỗi thuộc lớp tương thích nào?

**Gợi ý:** Dù bước đọc có thể tương thích ở mức serialization, **bất biến object và behavioral compatibility** chưa được bảo vệ. Cần migration/default hợp lệ trước khi dùng object trong logic.

**Tình huống 4.** Lớp `Task` dùng `hashCode` dựa trên `status`, và status thay đổi từ `QUEUED` thành `DONE` khi task đang là khóa `HashMap`. Có thể giữ thiết kế này không?

**Gợi ý:** Không an toàn nếu cần tra cứu lại cùng entry. Thiết kế khóa ổn định (`taskId`) hoặc cấu trúc theo trường trạng thái có quy trình remove–update–reinsert nhất quán.

**Ghi nhớ:** Khi thêm trường hoặc thay đổi phiên bản lớp, hãy trả lời đồng thời: **(1) thế nào là bằng nhau, (2) khóa có ổn định trong collection không, (3) caller cũ còn dùng được API/bytecode không, và (4) dữ liệu cũ/mới được chuyển đổi ra sao**. Đây là những quyết định hợp đồng cần chủ động kiểm thử và truyền đạt.