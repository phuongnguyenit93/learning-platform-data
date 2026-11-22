# Hợp đồng equals–hashCode và cách viết kiểu khóa

## 1. Bài toán: hai đối tượng có thể đại diện cùng một khóa

Một ứng dụng có thể tạo hai đối tượng khóa khác nhau để nói tới cùng một tài khoản:

```java
AccountKey first = new AccountKey("tenant-a", "u-7");
AccountKey second = new AccountKey("tenant-a", "u-7");
```

Hai biến không nhất thiết trỏ tới cùng đối tượng. Tuy nhiên, nếu quy tắc nghiệp vụ là “tài khoản được xác định bằng cặp tenantId và userId”, chúng cần được xem là cùng một khóa.

Điều này ảnh hưởng trực tiếp tới:

- Tra cứu bằng một đối tượng khóa mới có cùng dữ liệu.
- Thêm khóa tương đương vào `HashMap` để cập nhật giá trị.
- Loại trùng trong `HashSet`.
- Khả năng xóa hoặc kiểm tra tồn tại bằng một đối tượng tương đương.

Để các cấu trúc dựa trên bảng băm hoạt động đúng, kiểu khóa cần có quan hệ bằng nhau rõ ràng và mã băm nhất quán với quan hệ đó.

Bài sử dụng Java 17. Mục tiêu là hiểu hợp đồng, viết khóa bất biến đúng và nhận ra các lỗi thường chỉ lộ khi đối tượng được dùng trong collection.

## 2. Ba câu hỏi khác nhau: ==, equals và hashCode

| Cơ chế | Câu hỏi |
| --- | --- |
| `a == b` với tham chiếu | Hai tham chiếu có trỏ tới cùng một đối tượng không? |
| `a.equals(b)` | Hai đối tượng có bằng nhau theo hợp đồng của kiểu không? |
| `a.hashCode()` | Mã băm hỗ trợ phân nhóm/tìm kiếm trong cấu trúc băm là gì? |

Mặc định, `Object.equals` dùng quan hệ cùng đối tượng. Kiểu giá trị có thể override để định nghĩa bằng nhau theo dữ liệu.

`hashCode` trả `int`. Nó không phải ID duy nhất, không phải chữ ký mật mã và không có bảo đảm là địa chỉ bộ nhớ. Không lưu `hashCode` như định danh bền vững cho nghiệp vụ.

`equals` là nơi định nghĩa sự bằng nhau; việc hai mã băm bằng nhau không đủ để kết luận hai đối tượng bằng nhau.

Hợp đồng chính thức nằm trong [Object.equals và Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).

## 3. Hợp đồng equals cần giữ

Đối với các tham chiếu khác `null`, quan hệ bằng nhau phải có các tính chất sau:

| Tính chất | Điều kiện |
| --- | --- |
| Phản xạ | `x.equals(x)` là `true` |
| Đối xứng | `x.equals(y)` và `y.equals(x)` cho cùng kết quả |
| Bắc cầu | Nếu `x` bằng `y` và `y` bằng `z`, thì `x` bằng `z` |
| Nhất quán | Kết quả không đổi khi thông tin dùng để so sánh không đổi |
| Với `null` | `x.equals(null)` là `false` |

Đây không chỉ là quy ước trình bày. Nếu vi phạm đối xứng, kết quả có thể phụ thuộc phía thực hiện phép so sánh. Nếu vi phạm bắc cầu, một nhóm “cùng khóa” không còn được xác định nhất quán.

Phương thức phải có đúng chữ ký:

```java
@Override
public boolean equals(Object object)
```

Viết `equals(AccountKey other)` chỉ tạo overload nếu không đồng thời override `equals(Object)`. Các collection dùng hợp đồng `Object.equals`, nên overload đó không giải quyết được bài toán khóa. Dùng `@Override` để compiler giúp phát hiện sai chữ ký.

## 4. Hợp đồng hashCode và chiều suy luận đúng

Các quy tắc cốt lõi:

1. Khi thông tin tham gia `equals` không đổi trong một lần chạy, hash phải nhất quán.
2. Hai đối tượng bằng nhau phải có cùng hash.
3. Hai đối tượng khác nhau được phép có cùng hash.

Hash không bắt buộc giống nhau giữa các lần chạy chương trình. Không dùng quy tắc “khác nhau thì hash phải khác” làm kiểm thử tính đúng.

Có thể ghi nhớ:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()

a.hashCode() == b.hashCode()
    chưa đủ để kết luận a.equals(b) == true
```

Một hàm luôn trả `1` vẫn có thể đáp ứng yêu cầu hai đối tượng bằng nhau phải cùng hash. Nhưng nó gom rất nhiều khóa vào cùng nhóm ứng viên, làm giảm khả năng phân tán và có thể làm hiệu năng kém.

Ngược lại, một hàm tạo hash phân tán đẹp nhưng dùng thông tin không phù hợp với `equals` vẫn có thể sai về hợp đồng.

### Cần dùng các thông tin nhất quán

Nếu `equals` chỉ xét `tenantId` và `userId`, `hashCode` không nên thêm tên hiển thị thay đổi độc lập vào kết quả. Hai đối tượng bằng nhau theo cặp định danh có thể khác tên hiển thị, dẫn tới hash khác.

Thiết kế thông thường và dễ kiểm tra là dùng cùng các thành phần định nghĩa bằng nhau cho cả hai phương thức. Hash không bắt buộc “dùng đủ mọi trường”; điều cần bảo đảm là nhất quán với quan hệ bằng nhau, đồng thời phân tán hợp lý.

## 5. HashMap và HashSet sử dụng hợp đồng như thế nào?

Ở mức mô hình, cấu trúc băm dùng hash để thu hẹp nhóm ứng viên, rồi phân biệt khóa theo quan hệ bằng nhau. Không nên coi đây là lời hứa về số lần chính xác mà `equals` hoặc `hashCode` được gọi.

### 5.1. Khóa bằng nhau trong map

Nếu `first` và `second` là các khóa bằng nhau và có hash đúng:

```java
// Đoạn minh họa với AccountKey được định nghĩa ở phần chương trình đầy đủ.
Map<AccountKey, String> map = new HashMap<>();
map.put(first, "old");

System.out.println(map.get(second));        // old
System.out.println(map.put(second, "new")); // old
System.out.println(map.size());             // 1
```

Lần `put` sau cập nhật giá trị của mapping có khóa tương đương, không tạo thêm một tài khoản khác theo quan hệ khóa.

### 5.2. Phần tử bằng nhau trong set

```java
// Đoạn minh họa với hai AccountKey bằng nhau; cần import java.util.*.
Set<AccountKey> keys = new HashSet<>();
System.out.println(keys.add(first));  // true
System.out.println(keys.add(second)); // false
```

Set loại trùng theo hợp đồng phần tử. Nếu phần tử có `equals/hashCode` sai, kết quả loại trùng và tìm kiếm có thể không đáp ứng ý định nghiệp vụ.

Xem [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) và [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### 5.3. Va chạm băm không làm hai khóa thành một

Hai khóa khác nhau có thể cùng hash. Cấu trúc vẫn phải phân biệt chúng theo hợp đồng bằng nhau.

Vì vậy, không cài đặt:

```java
// Minh họa cách viết sai; không sử dụng.
return this.hashCode() == other.hashCode();
```

như toàn bộ định nghĩa `equals`.

Cũng không đưa thông tin hash vào điều kiện nghiệp vụ kiểu “mã băm trùng nên đây là cùng người dùng”. Hash chỉ có vai trò hỗ trợ cấu trúc tra cứu.

## 6. Chọn đúng dữ liệu định nghĩa khóa trước khi viết code

Với khóa tài khoản đa tenant, `userId` có thể chỉ duy nhất trong từng tenant. Bỏ `tenantId` khỏi `equals` sẽ gộp hai tài khoản thuộc hai tenant khác nhau.

Cần xác định:

- Phạm vi duy nhất của từng thành phần.
- Phân biệt chữ hoa/chữ thường.
- Chính sách khoảng trắng và chuẩn hóa.
- Có cho phép `null` hoặc giá trị rỗng không.
- Định danh có ổn định trong suốt thời gian khóa được lưu không.

Ví dụ bài này chọn chính sách đơn giản: hai chuỗi bắt buộc khác `null`, so sánh chính xác, có phân biệt chữ hoa/thường, không tự cắt khoảng trắng.

Không tự gọi `toLowerCase` hoặc `trim` trong một phía của `equals` rồi dùng dữ liệu gốc để băm. Nếu nghiệp vụ cần chuẩn hóa, hãy xác định một quy tắc nhất quán, thực hiện tại lúc tạo khóa và dùng biểu diễn đã chuẩn hóa ở cả hai phương thức.

Các giá trị có cấu trúc nên được giữ thành thành phần riêng. Ghép hai trường thành chuỗi mà không có quy tắc phân tách rõ có thể làm mất ranh giới dữ liệu.

## 7. Viết một lớp khóa bất biến

Một mẫu dễ kiểm tra:

```java
// Đoạn khai báo lớp; cần import java.util.Objects.
static final class AccountKey {
    private final String tenantId;
    private final String userId;

    AccountKey(String tenantId, String userId) {
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
        this.userId = Objects.requireNonNull(userId, "userId");
    }

    @Override
    public boolean equals(Object object) {
        if (this == object) {
            return true;
        }
        if (!(object instanceof AccountKey other)) {
            return false;
        }
        return tenantId.equals(other.tenantId)
                && userId.equals(other.userId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, userId);
    }
}
```

Từng quyết định có mục đích:

- `final class` giữ miền so sánh không bị lớp con mở rộng ngoài thiết kế.
- Hai trường `final` và kiểu `String` bất biến làm thông tin khóa ổn định.
- Constructor quy định hai thành phần khác `null`.
- `this == object` là đường tắt cho cùng đối tượng.
- `instanceof` trả `false` khi đối số là `null` hoặc khác kiểu.
- Hai trường được so bằng `String.equals` thay vì `==`.
- Hash được tính từ các thành phần cùng định nghĩa bằng nhau.

`Objects.hash` là tiện ích băm nhiều thành phần; không phải thuật toán mã hóa hoặc bảo đảm không va chạm. `Objects.equals` cũng hữu ích khi một trường được phép `null`, nhưng chính sách khóa mẫu đã từ chối `null` từ constructor. [Objects API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html)

Có thể dùng công cụ sinh code của IDE, nhưng vẫn phải chọn đúng trường và hiểu hợp đồng được sinh. Sinh code đúng cú pháp không tự chọn đúng danh tính nghiệp vụ.

## 8. Kế thừa và miền bằng nhau

Khi lớp khóa có thể được kế thừa, câu hỏi khó xuất hiện: đối tượng lớp cha có được xem bằng lớp con không, và các trường mới ở lớp con có tham gia bằng nhau không?

Ví dụ, lớp cha chỉ có tọa độ; lớp con thêm màu. Nếu cha chấp nhận mọi đối tượng cùng tọa độ còn con đòi thêm màu, có thể xảy ra:

```text
cha.equals(con) = true
con.equals(cha) = false
```

Đây là vi phạm đối xứng. Những cách “linh động bỏ qua màu trong một số trường hợp” còn có thể làm hỏng bắc cầu.

Không có một thay thế máy móc `instanceof` hoặc `getClass` nào giải quyết mọi mô hình kế thừa. Trước hết cần quyết định miền đối tượng được coi bằng nhau.

Với kiểu khóa giá trị mới, các lựa chọn thường dễ quản lý là:

- Dùng một lớp `final`.
- Dùng record có các component phù hợp.
- Dùng kết hợp đối tượng thay cho mở rộng một quan hệ bằng nhau chưa được thiết kế.

Nếu bắt buộc thiết kế phân cấp có bằng nhau xuyên lớp, phải kiểm tra đối xứng, bắc cầu và hash trên toàn miền đó. Bài mẫu dùng lớp cuối để giữ hợp đồng rõ ràng.

## 9. Khóa thay đổi sau khi chèn: vì sao tra cứu có thể thất bại?

Giả sử một khóa dùng trường `id` trong cả `equals` và `hashCode`. Sau khi chèn, mã sửa `id` từ `1` thành `2`.

Thông tin dùng để tìm khóa đã thay đổi, trong khi cấu trúc băm không được thông báo để sắp xếp lại mapping tương ứng.

Có thể thấy tình huống:

```text
map.size() vẫn là 1
iterator vẫn nhìn thấy đối tượng khóa
map.get(chính đối tượng đó) lại không tìm được
```

Đây không phải lỗi “map quên giữ tham chiếu”. Đối tượng vẫn tồn tại; cách tìm kiếm theo khóa đã không còn tương thích với trạng thái dùng lúc lưu.

Hợp đồng `Map` nói rõ hành vi không được quy định khi đối tượng khóa bị đổi theo cách ảnh hưởng `equals` trong lúc đang là khóa. `Set` có giới hạn tương tự với phần tử ảnh hưởng quan hệ bằng nhau. Kết quả tra cứu trong chương trình đầy đủ là minh họa được quan sát với `HashMap` đang chạy, không phải một hành vi mới có thể dùng làm quy tắc ứng dụng. [Map contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

### Cách xử lý đúng

Ưu tiên khóa bất biến. Khi cần “đổi định danh”, tạo một đối tượng khóa mới và cập nhật mapping có kiểm soát.

Nếu đang quản lý một khóa mutable, phải xóa mapping bằng trạng thái cũ trước khi thay đổi rồi chèn lại với trạng thái mới, trong một quy trình bảo đảm không có truy cập cạnh tranh ngoài kiểm soát. Sau khi khóa đã bị sửa, đừng giả định `remove(key)` chắc chắn tìm được nó để chữa lỗi.

Việc thay trường không tham gia `equals/hashCode` không nhất thiết làm đổi danh tính khóa, nhưng vẫn cần xét các ràng buộc khác. “Có setter” không tự động là lỗi; lỗi cốt lõi là dữ liệu quyết định định vị/bằng nhau thay đổi khi đối tượng đang được dùng theo hợp đồng cần ổn định.

## 10. Record: ngắn gọn nhưng phải chọn component đúng

Đây là phương án thay thế lớp `AccountKey` ở trên; không khai báo cả hai cùng tên trong cùng phạm vi. Chương trình đầy đủ dùng tên `RecordKey` để đặt hai cách viết cạnh nhau.

```java
// Đoạn khai báo record; cần import java.util.Objects.
record AccountKey(String tenantId, String userId) {
    AccountKey {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(userId, "userId");
    }
}
```

Record tự cung cấp `equals/hashCode` theo các component và kiểm tra cùng lớp record. Nó phù hợp với khóa giá trị khi các component biểu đạt đúng danh tính và có trạng thái ổn định.

Các điểm cần giữ rõ:

- Thêm một component như tên hiển thị cũng làm nó tham gia quan hệ mặc định.
- Component là tham chiếu `final`, nhưng đối tượng được tham chiếu có thể thay đổi.
- Record chứa collection mutable có thể có hash thay đổi theo nội dung collection.
- Record chứa mảng không tự có phép bằng nhau sâu theo nội dung mảng.
- Không phụ thuộc một giá trị hash số cụ thể hoặc thuật toán kết hợp component được quan sát.

Nếu muốn record chứa một danh sách chuỗi làm khóa, có thể sao chép phòng vệ bằng `List.copyOf` trong constructor, đồng thời chấp nhận chính sách cấm phần tử `null` và hiểu rằng đó là bản sao nông. Với phần tử mutable, cần một thiết kế sâu hơn.

Xem [Record API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html), [Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html) và [JLS 8.10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).

## 11. Khóa có mảng cần bằng nhau nội dung và sao chép phòng vệ

Mảng dùng quan hệ bằng nhau theo tham chiếu của `Object` nếu chỉ gọi `array.equals`. Hai mảng byte riêng có cùng nội dung không tự bằng nhau.

Để định nghĩa khóa theo nội dung byte:

- Dùng `Arrays.equals` cho bằng nhau.
- Dùng `Arrays.hashCode` tương ứng cho băm.
- Sao chép mảng đầu vào.
- Không trả trực tiếp mảng nội bộ cho người gọi sửa.

```java
// Đoạn khai báo lớp; cần import java.util.Arrays và java.util.Objects.
static final class BytesKey {
    private final byte[] bytes;

    BytesKey(byte[] bytes) {
        this.bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object object) {
        return object instanceof BytesKey other
                && Arrays.equals(bytes, other.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
```

Chỉ khai báo `private final byte[]` chưa đủ: `final` cố định tham chiếu nhưng không cố định các phần tử.

Cũng không thay `Arrays.hashCode(bytes)` bằng `Objects.hash(bytes)` rồi giả định đó là băm nội dung byte tương đương. Với mảng nguyên thủy truyền như một đối tượng cho varargs, cách xử lý không phải phép băm từng phần tử byte mà khóa nội dung đang cần.

Với mảng lồng nhau hoặc mảng đối tượng, cần chọn `equals/deepEquals` và `hashCode/deepHashCode` theo chính xác mức nội dung được coi là danh tính. Không trộn phép so sánh sâu với hash chỉ dựa trên tham chiếu. [Arrays API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)

## 12. Bằng nhau, sắp thứ tự và một số giá trị đặc biệt

`HashMap/HashSet` dựa vào hợp đồng băm/bằng nhau. `TreeMap/TreeSet` định vị theo `compareTo` hoặc comparator. Để đáp ứng hợp đồng chung của map/set, thứ tự cần nhất quán với `equals`.

Ví dụ, `BigDecimal("1.0")` và `BigDecimal("1.00")` có `compareTo` trả `0` nhưng `equals` là `false` do khác scale. Khi chọn kiểu khóa và cấu trúc, phải hiểu “bằng nhau theo số học” và “bằng nhau của kiểu” có thể khác.

Không cố sửa hash để biến một comparator không nhất quán thành đúng. Cần thiết kế quan hệ bằng nhau và thứ tự theo cùng ý định, hoặc lựa chọn mô hình có chủ đích và hiểu giới hạn hợp đồng.

Nguồn: [TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html), [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

Khi khóa có số thực, cần chọn ngữ nghĩa rõ cho `NaN` và zero có dấu; dùng cách so sánh/băm thống nhất của kiểu wrapper hoặc công cụ sinh code phù hợp. Không tự thêm quy tắc “gần bằng trong một epsilon” vào `equals` mà không xét bắc cầu.

Với định danh được cấp sau khi tạo đối tượng, chẳng hạn ID tạm thời chưa có giá trị, cũng cần xác định lúc nào đối tượng có một danh tính ổn định. Không mặc định mọi đối tượng có ID `null` đều là cùng một khóa.

## 13. Chương trình hoàn chỉnh

Lưu thành `EqualityKeyDemo.java`.

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class EqualityKeyDemo {
    static final class AccountKey {
        private final String tenantId;
        private final String userId;

        AccountKey(String tenantId, String userId) {
            this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
            this.userId = Objects.requireNonNull(userId, "userId");
        }

        @Override
        public boolean equals(Object object) {
            if (this == object) {
                return true;
            }
            if (!(object instanceof AccountKey other)) {
                return false;
            }
            return tenantId.equals(other.tenantId)
                    && userId.equals(other.userId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, userId);
        }
    }

    record RecordKey(String tenantId, String userId) {
        RecordKey {
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(userId, "userId");
        }
    }

    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void setId(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof MutableKey other && id == other.id;
        }

        @Override
        public int hashCode() {
            return id;
        }
    }

    static final class CollisionKey {
        private final int id;

        CollisionKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof CollisionKey other && id == other.id;
        }

        @Override
        public int hashCode() {
            return 1;
        }
    }

    static final class BytesKey {
        private final byte[] bytes;

        BytesKey(byte[] bytes) {
            this.bytes = Objects.requireNonNull(bytes, "bytes").clone();
        }

        byte[] bytes() {
            return bytes.clone();
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof BytesKey other
                    && Arrays.equals(bytes, other.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }
    }

    public static void main(String[] args) {
        AccountKey first = new AccountKey("tenant-a", "u-7");
        AccountKey equal = new AccountKey("tenant-a", "u-7");
        AccountKey otherTenant = new AccountKey("tenant-b", "u-7");

        System.out.println("Same reference: " + (first == equal));
        System.out.println("Equal content: " + first.equals(equal));
        System.out.println("Equal hash: "
                + (first.hashCode() == equal.hashCode()));
        System.out.println("Different tenant equal: "
                + first.equals(otherTenant));

        Map<AccountKey, String> users = new HashMap<>();
        users.put(first, "old");
        System.out.println("Lookup with equal key: " + users.get(equal));
        System.out.println("Previous value: " + users.put(equal, "new"));
        System.out.println("Map size: " + users.size());

        Set<AccountKey> keys = new HashSet<>();
        System.out.println("First set add: " + keys.add(first));
        System.out.println("Equal set add: " + keys.add(equal));

        RecordKey recordA = new RecordKey("tenant-a", "u-7");
        RecordKey recordB = new RecordKey("tenant-a", "u-7");
        System.out.println("Record equality: " + recordA.equals(recordB));

        Map<CollisionKey, String> collisions = new HashMap<>();
        collisions.put(new CollisionKey(1), "one");
        collisions.put(new CollisionKey(2), "two");
        System.out.println("Collision map size: " + collisions.size());
        System.out.println("Collision lookup: "
                + collisions.get(new CollisionKey(2)));

        MutableKey mutable = new MutableKey(1);
        Map<MutableKey, String> unsafe = new HashMap<>();
        unsafe.put(mutable, "value");
        mutable.setId(2);
        System.out.println("Mutated key same reference present: "
                + (unsafe.keySet().iterator().next() == mutable));
        System.out.println("Mutated key lookup: " + unsafe.get(mutable));
        System.out.println("Mutated map size: " + unsafe.size());

        byte[] input = {1, 2};
        BytesKey bytesKey = new BytesKey(input);
        input[0] = 9;
        byte[] returned = bytesKey.bytes();
        returned[1] = 9;
        System.out.println("Defensive bytes equality: "
                + bytesKey.equals(new BytesKey(new byte[] {1, 2})));

        record ArrayRecord(byte[] bytes) {}
        System.out.println("Array record equality: "
                + new ArrayRecord(new byte[] {1, 2})
                        .equals(new ArrayRecord(new byte[] {1, 2})));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:unchecked EqualityKeyDemo.java
java EqualityKeyDemo
```

Mã đã được kiểm tra theo nền API Java 17 trên một JDK mới hơn, không có cảnh báo unchecked.

Stdout quan sát được:

```text
Same reference: false
Equal content: true
Equal hash: true
Different tenant equal: false
Lookup with equal key: old
Previous value: old
Map size: 1
First set add: true
Equal set add: false
Record equality: true
Collision map size: 2
Collision lookup: two
Mutated key same reference present: true
Mutated key lookup: null
Mutated map size: 1
Defensive bytes equality: true
Array record equality: false
```

### Giải thích kết quả

- Hai `AccountKey` là hai đối tượng riêng nên `==` trả `false`, nhưng cùng cặp định danh nên `equals` là `true` và hash bằng nhau.
- Khác tenant làm khóa khác dù cùng user ID.
- Tra cứu bằng khóa tương đương trả mapping ban đầu; `put` cập nhật giá trị nên kích thước map vẫn `1`.
- Set từ chối thêm phần tử bằng nhau lần hai.
- Record với hai component chuỗi có quan hệ bằng nhau giá trị phù hợp.
- `CollisionKey` luôn trả cùng hash nhưng `equals` vẫn phân biệt ID, nên map giữ được hai mapping.
- `MutableKey` bị đổi sau khi chèn: chương trình quan sát khóa vẫn nằm trong map nhưng `get` không tìm được. Đây là tình huống đã vượt điều kiện sử dụng được bảo đảm; không dựa vào đúng kết quả này ở các chương trình khác.
- `BytesKey` vẫn giữ nội dung `1, 2` sau khi mảng đầu vào và mảng trả ra bị sửa, nhờ sao chép phòng vệ.
- Hai record chứa hai mảng byte riêng có cùng nội dung vẫn không bằng nhau theo cài đặt record mặc định.

Ví dụ cố ý giữ `MutableKey` và `CollisionKey` chỉ để minh họa rủi ro và hợp đồng, không đề xuất chúng làm khóa sản xuất.

## 14. Kiểm tra một kiểu khóa trước khi sử dụng

Với ít nhất ba đối tượng riêng cùng dữ liệu và các đối tượng khác từng thành phần, cần kiểm tra:

1. Phản xạ, đối xứng, bắc cầu.
2. So với `null` và một kiểu khác.
3. Kết quả ổn định khi trạng thái liên quan không đổi.
4. Hai đối tượng bằng nhau có hash bằng nhau.
5. Khác một thành phần danh tính làm `equals` khác nếu nghiệp vụ quy định.
6. Tra cứu/xóa bằng một khóa mới tương đương trong `HashMap`.
7. Loại trùng đúng trong `HashSet`.
8. Constructor và getter không làm lộ trạng thái mutable quyết định hash.
9. Các trường hợp biên như chuỗi rỗng, Unicode, `null` nếu được phép, mảng và component lồng nhau.
10. Tính nhất quán với comparator nếu kiểu dùng trong cấu trúc có thứ tự.

Không yêu cầu hai đối tượng khác nhau phải có hash khác trong kiểm thử tính đúng. Có thể đánh giá phân bố hash/hiệu năng riêng trên dữ liệu đại diện, nhưng đừng biến mong muốn hiệu năng thành một hợp đồng không tồn tại.

Không kiểm thử bằng con số hash cụ thể của record. Kiểm thử quan hệ mà ứng dụng cần: bằng nhau, ổn định và truy cập collection đúng.

## 15. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Override `equals` nhưng giữ hash mặc định | Các đối tượng bằng nhau có thể không được tìm như cùng khóa | Cài đặt cả hai theo cùng danh tính |
| Viết `equals(MyKey)` thay vì `equals(Object)` | Chỉ overload, collection không dùng hợp đồng mong muốn | Dùng đúng chữ ký và `@Override` |
| So chuỗi bằng `==` | Phụ thuộc việc chia sẻ đối tượng | Dùng `String.equals` hoặc `Objects.equals` |
| Dùng hash bằng nhau làm định nghĩa equals | Gộp khóa do va chạm | So sánh dữ liệu danh tính |
| Hash dùng trường không được equals xét | Có thể vi phạm equal ⇒ same hash | Chọn thông tin nhất quán |
| Dùng mọi trường mutable làm danh tính | Hash/equals thay đổi trong collection | Tách khóa ổn định khỏi dữ liệu thay đổi |
| Chỉ dùng `final` cho mảng/collection | Nội dung vẫn có thể đổi | Sao chép phòng vệ và kiểm soát phần tử |
| Cho lớp con mở rộng equality tùy ý | Dễ phá đối xứng/bắc cầu | Thiết kế miền so sánh; cân nhắc lớp cuối hoặc kết hợp |
| Coi record là bất biến sâu | Component có thể giữ đối tượng mutable | Kiểm tra component và sao chép đúng mức |
| Sửa khóa rồi gọi `remove` để chữa | Có thể không tìm được theo trạng thái mới | Giữ khóa ổn định; cập nhật mapping có kiểm soát |
| Lưu hash như ID nghiệp vụ | Va chạm và thiếu bảo đảm bền vững | Dùng định danh được thiết kế cho mục đích đó |

## 16. Tự kiểm tra và thực hành

### Câu hỏi

1. Hai khóa có cùng dữ liệu nhưng `==` là `false` có thể `equals` là `true` không?
2. Nếu `a.equals(b)` là `true`, hash phải thỏa điều gì?
3. Hai hash bằng nhau có đủ kết luận cùng khóa không?
4. Vì sao bỏ tenant khỏi khóa đa tenant là lỗi thiết kế dù code đúng cú pháp?
5. `equals(AccountKey)` khác `equals(Object)` thế nào?
6. Vì sao hash không nên dùng trường thay đổi ngoài danh tính equality?
7. Có phải `private final byte[]` tự tạo khóa bất biến?
8. Record chứa mảng có tự so sánh nội dung mảng không?
9. Vì sao map còn giữ đối tượng khóa nhưng tra cứu lại có thể thất bại sau khi sửa khóa?
10. `TreeMap` dùng quan hệ nào để định vị khóa và cần nhất quán ra sao?

### Bài tập

- Viết khóa `ProductKey` gồm `shopId` và `sku`, có chính sách `null` rõ ràng.
- Tạo ba đối tượng riêng cùng dữ liệu và kiểm tra các tính chất của `equals`.
- Dùng một đối tượng để `put` và một đối tượng tương đương để `get/remove`.
- Đưa các khóa tương đương vào `HashSet` và kiểm tra số phần tử.
- Tạo phiên bản record của khóa, so sánh mức code cần viết và các giả định về component.
- Thêm trường tên hiển thị vào mô hình dữ liệu nhưng không vào khóa; giải thích vì sao định danh vẫn ổn định.
- Viết khóa có dữ liệu byte, kiểm tra sửa mảng đầu vào hoặc getter không làm đổi hash nội bộ.
- Thử va chạm hash có chủ đích trong môi trường học, chứng minh hai khóa khác nhau vẫn tồn tại.
- Đối chiếu `BigDecimal` làm khóa trong cấu trúc băm và cấu trúc sắp thứ tự, nêu rõ quan hệ bằng nhau được quan sát.

### Gợi ý đối chiếu

1. Có; bằng nhau giá trị khác với cùng tham chiếu.
2. Hai hash phải bằng nhau.
3. Không; va chạm được phép.
4. Quan hệ bằng nhau đã gộp các danh tính nghiệp vụ khác nhau.
5. Chữ ký đầu chỉ overload nếu không có override đúng; chữ ký sau là hợp đồng Object.
6. Hai đối tượng bằng nhau có thể khác trường đó, tạo hash khác.
7. Không; chỉ tham chiếu là final, các phần tử vẫn thay đổi được.
8. Không; cần định nghĩa equality/hash theo nội dung nếu đó là ý định.
9. Trạng thái định vị đã đổi trong khi cấu trúc chưa được xây lại; điều kiện Map không còn được bảo đảm.
10. Dùng compareTo/comparator; thứ tự cần nhất quán với equals để đáp ứng hợp đồng chung.
