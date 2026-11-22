# Chỉ lưu sẵn hash code khi trạng thái và cơ chế đồng bộ cho phép

`hashCode()` là một phần của hợp đồng bằng nhau giữa các đối tượng Java. Khi tính mã băm tốn chi phí, ta có thể **lưu sẵn (cache, memoization)** kết quả để tái sử dụng. Nhưng một trường `cachedHash` chỉ đúng nếu kết quả đó còn đại diện cho trạng thái mà `equals()` xem là danh tính logic, và nếu nhiều luồng truy cập thì việc công bố cũng như đọc/ghi giá trị đã được thiết kế đúng.

Ba câu hỏi phải được giải quyết trước khi lưu hash:

1. **Trạng thái nào quyết định `equals()` và `hashCode()`?** Trạng thái ấy có giữ nguyên trong suốt vòng đời đối tượng hoặc ít nhất trong thời gian sử dụng cache không?
2. **Hash được tính và công bố như thế nào?** Có luồng khác truy cập trước hoặc đồng thời khi cache được gán không?
3. **Đối tượng được dùng ở đâu?** Nếu đã làm khóa `HashMap` hoặc phần tử `HashSet`, việc thay đổi giá trị quyết định hash có thể làm mất khả năng tra cứu ngay cả khi cache được cập nhật đúng.

Mục tiêu là bảo vệ tính đúng đắn trước rồi mới tối ưu hiệu năng.

## 1. Hợp đồng `equals()` – `hashCode()` quyết định việc có được cache

Với hai đối tượng `a`, `b`:

- Nếu `a.equals(b)` trả `true`, **bắt buộc** `a.hashCode() == b.hashCode()`.
- Hai đối tượng khác nhau **được phép** có mã băm giống nhau: va chạm hash không có nghĩa chúng bằng nhau.
- Trong một lần chạy Java, nếu những thông tin được sử dụng cho phép so sánh bằng nhau **không đổi**, việc gọi `hashCode()` nhiều lần trên cùng đối tượng phải cho kết quả nhất quán.
- Nếu các thông tin dùng trong phép so sánh **thay đổi**, kết quả hash có thể thay đổi; nhưng cần tránh thay đổi khi đối tượng đang được sử dụng như khóa của cấu trúc hash.

Hash được cache là một **giá trị dẫn xuất** từ trạng thái. Khi trạng thái logic đã đổi, cache có thể thành **giá trị cũ (stale cache)**. Ví dụ, đối tượng đang có `code = "B"` nhưng trường cache chứa hash của `"A"`. Một đối tượng khác cũng có `code = "B"` sẽ bằng nhau theo `equals()` nhưng có thể trả một mã băm khác. Đó là lỗi hợp đồng, dù mọi phương thức đều có thể chạy không ném exception.

Cũng không được hiểu `hashCode()` là một ID duy nhất, bất biến theo mọi trường hợp. Mã hash có thể va chạm; tính ổn định phải được thiết kế theo **các trường tham gia equality**.

## 2. Chọn chiến lược theo tính chất trạng thái

| Trường hợp | Khuyến nghị | Lý do |
| --- | --- | --- |
| Value object bất biến; hash thường được sử dụng | Có thể **tính trước** và lưu trong trường `final` | Không phải xử lý invalidation và visibility của một lần ghi cache muộn |
| Value object bất biến; hash đắt nhưng ít được gọi | Có thể **tính lười** với cơ chế công bố an toàn | Tránh tính hash cho những instance không bao giờ cần |
| Object mutable chỉ dùng nội bộ một luồng | Cache có điều kiện; phải vô hiệu hóa khi trạng thái liên quan đổi | Tránh trả lại kết quả cũ |
| Object mutable nhiều luồng cùng truy cập | Cân nhắc thiết kế lại; muốn cache cần nhất quán cho trạng thái, cache và `equals()` | `volatile` riêng cache không đồng bộ các trường trạng thái khác |
| Object mutable đã nằm trong `HashMap`/`HashSet` | Tránh thay đổi các trường dùng cho equality/hash | Invalidation không điều chỉnh vị trí phần tử trong cấu trúc hash |
| Hash tính rẻ, hiếm gọi | Thường cứ tính trực tiếp | Cache tốn bộ nhớ, nhánh điều kiện và đôi khi đồng bộ |

Không nên chỉ thấy `private final List<String> items` mà kết luận trạng thái bất biến: `final` cố định **tham chiếu**, nhưng `List` bên trong vẫn có thể thay đổi. Nếu nội dung danh sách tham gia phép tính hash, cần sao chép phòng vệ và giữ nội dung thực sự bất biến, hoặc chọn một thiết kế khác.

## 3. Cache tính sớm: đơn giản nhất với đối tượng bất biến

Khi mọi trường tham gia `equals()` đều bất biến, ta có thể tính hash một lần trong constructor, lưu vào một trường `final`. Đó là cách tránh việc phải xử lý cache bị lỗi thời.

Tạo file **`EagerHashDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class AccountKey {
    private final String tenant;
    private final String account;
    private final int cachedHash;

    AccountKey(String tenant, String account) {
        this.tenant = Objects.requireNonNull(tenant);
        this.account = Objects.requireNonNull(account);
        this.cachedHash = Objects.hash(tenant, account);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof AccountKey other
                && tenant.equals(other.tenant)
                && account.equals(other.account);
    }

    @Override
    public int hashCode() {
        return cachedHash;
    }
}

public class EagerHashDemo {
    public static void main(String[] args) {
        AccountKey a = new AccountKey("north", "001");
        AccountKey b = new AccountKey("north", "001");
        AccountKey c = new AccountKey("south", "001");

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));

        Set<AccountKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);
        keys.add(c);
        System.out.println("set size: " + keys.size());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac EagerHashDemo.java
java EagerHashDemo
```

Stdout:

```text
a equals b: true
same hash: true
set size: 2
```

**Vì sao mẫu này hợp lệ?**

- `tenant` và `account` không null, thuộc kiểu `String` bất biến và được gán một lần.
- `equals()` và phép tính `Objects.hash(tenant, account)` sử dụng **cùng hai thành phần**.
- `cachedHash` là `final`, được gán ngay trong constructor, không có setter.
- `AccountKey` là lớp `final`, ngăn subclass bổ sung trạng thái nhưng kế thừa quy tắc bằng nhau cũ.
- Đối tượng được tạo đúng cách: không để tham chiếu `this` thoát khỏi constructor. Java Memory Model có quy tắc khởi tạo đặc biệt cho `final` fields; tuy vậy, cần tuân thủ cách công bố đối tượng an toàn cho các phần trạng thái khác nếu có.

`Objects.hash()` dễ đọc, nhưng do sử dụng varargs, nó có chi phí bổ sung so với một công thức hash thủ công. Chỉ tối ưu công thức sau khi đo đạc, luôn giữ nhất quán với `equals()`.

**Phân biệt:** tính sớm làm constructor thêm việc, kể cả khi không ai gọi `hashCode()`. Với đối tượng nhỏ và phép hash đơn giản, không có lý do phải lưu sẵn hash nếu đo đạc không cho thấy lợi ích.

## 4. Cache tính lười: phải giải quyết công bố kết quả giữa các luồng

**Lazy caching** chỉ tính hash ở lần gọi đầu tiên. Nếu đối tượng bất biến, hai luồng có thể cùng tính hash dựa trên cùng dữ liệu và nhận cùng kết quả. Trường hợp đó, tính trùng chỉ làm hao công; tính đúng đắn không bị ảnh hưởng nếu phép tính **thuần, tất định**, và kết quả được công bố an toàn.

Một cách dễ kiểm chứng là lưu hash trong trường **`volatile Integer`**, dùng `null` biểu thị chưa tính:

```java
private volatile Integer cachedHash;

@Override
public int hashCode() {
    Integer local = cachedHash;
    if (local != null) {
        return local;
    }

    int computed = immutableCode.hashCode();
    cachedHash = computed;
    return computed;
}
```

Đây là **mảnh code minh họa**, giả định lớp có trường `immutableCode` bất biến. Từ khóa `volatile` đảm bảo khi một luồng đọc được tham chiếu cache đã được công bố, nó quan sát giá trị phù hợp; việc gán một tham chiếu vào trường volatile là nguyên tử. Hai luồng vẫn có thể cùng thấy `null` và cùng tính, nhưng với dữ liệu bất biến, cả hai đều công bố cùng giá trị.

### 4.1. Ví dụ đầy đủ, bao gồm hash bằng 0

Tạo file **`LazyHashDemo.java`**:

```java
import java.util.Objects;

final class LazyKey {
    private final String code;
    private volatile Integer cachedHash;

    LazyKey(String code) {
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof LazyKey other
                && code.equals(other.code);
    }

    @Override
    public int hashCode() {
        Integer local = cachedHash;
        if (local != null) {
            return local;
        }

        int computed = code.hashCode();
        cachedHash = computed;
        return computed;
    }
}

public class LazyHashDemo {
    public static void main(String[] args) {
        LazyKey first = new LazyKey("");
        LazyKey second = new LazyKey("");

        System.out.println("first hash: " + first.hashCode());
        System.out.println("repeat hash: " + first.hashCode());
        System.out.println("equals: " + first.equals(second));
        System.out.println("same hash: "
                + (first.hashCode() == second.hashCode()));
    }
}
```

Lệnh:

```bash
javac LazyHashDemo.java
java LazyHashDemo
```

Stdout:

```text
first hash: 0
repeat hash: 0
equals: true
same hash: true
```

`String.hashCode()` của chuỗi rỗng là `0`. Nếu dùng một trường `int cachedHash = 0` rồi cho `0` nghĩa là “chưa tính”, đối tượng có hash thực sự bằng 0 có thể phải tính lại mãi. Điều đó **không nhất thiết sai kết quả**, nhưng phá kỳ vọng “chỉ tính một lần”. Dùng `Integer` nullable, một cờ đã khởi tạo riêng hoặc một cấu trúc kết quả khác để phân biệt.

**Chi phí cần cân nhắc:** `Integer` có boxing, trường `volatile` có chi phí truy cập và lazy init có nhánh điều kiện. Đối với hash rẻ, việc dùng trực tiếp `code.hashCode()` có thể đơn giản hơn. Đây là **mẫu đúng về semantics**, không phải tuyên bố rằng cache luôn nhanh hơn.

### 4.2. Khi nào cần `synchronized`?

Nếu bản thân phép tính hash rất nặng hoặc có giới hạn tài nguyên nên cần **đúng một lần tính**, có thể bảo vệ việc kiểm tra và cập nhật cache bằng `synchronized` hoặc một cơ chế khởi tạo đồng bộ tương đương. Tuy vậy, đồng bộ không miễn phí và cũng không thay thế yêu cầu dữ liệu dùng tính hash phải có snapshot ổn định.

Không áp dụng double-checked locking một cách máy móc: mẫu đó đòi hỏi thiết kế visibility/công bố đúng với Java Memory Model và chỉ đáng dùng nếu thật sự có lợi ích. Nếu `hashCode()` có side effect, lấy giá trị ngẫu nhiên, đọc đồng hồ hoặc phụ thuộc dữ liệu bên ngoài biến đổi, vấn đề còn nằm ở **thiết kế hàm hash không nhất quán**.

## 5. Lỗi cache stale khi đối tượng mutable

Nếu thuộc tính tham gia `equals()` thay đổi mà cache không được invalidation, hai đối tượng có thể bằng nhau nhưng báo hash khác nhau.

Tạo file **`StaleHashDemo.java`**:

```java
import java.util.Objects;

final class MutableKey {
    private String code;
    private Integer cachedHash;

    MutableKey(String code) {
        this.code = Objects.requireNonNull(code);
    }

    void changeCode(String newCode) {
        code = Objects.requireNonNull(newCode);
        // Lỗi cố ý: không xóa cachedHash.
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof MutableKey other
                && code.equals(other.code);
    }

    @Override
    public int hashCode() {
        if (cachedHash == null) {
            cachedHash = code.hashCode();
        }
        return cachedHash;
    }
}

public class StaleHashDemo {
    public static void main(String[] args) {
        MutableKey a = new MutableKey("A");
        System.out.println("before: " + a.hashCode());

        a.changeCode("B");
        MutableKey b = new MutableKey("B");

        System.out.println("after: " + a.hashCode());
        System.out.println("b hash: " + b.hashCode());
        System.out.println("equals: " + a.equals(b));
        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));
    }
}
```

Lệnh:

```bash
javac StaleHashDemo.java
java StaleHashDemo
```

Stdout:

```text
before: 65
after: 65
b hash: 66
equals: true
same hash: false
```

`"A".hashCode()` là 65, `"B".hashCode()` là 66. Sau khi `a` đổi `code` thành `"B"`, `equals()` đánh giá `a` và `b` bằng nhau, nhưng `a.hashCode()` tiếp tục dùng cache cũ 65. **Vi phạm trực tiếp hợp đồng `equals()`/`hashCode()`.** Đây là ví dụ lỗi có chủ ý, chỉ dùng để học.

### 5.1. Vô hiệu hóa cache ở setter là cần nhưng chưa đủ

Với đối tượng mutable và sử dụng trong một luồng được kiểm soát, có thể vô hiệu hóa cache khi giá trị liên quan thay đổi:

```java
void changeCode(String newCode) {
    code = Objects.requireNonNull(newCode);
    cachedHash = null;
}
```

Đây chỉ là **mảnh code cho bối cảnh một luồng hoặc có đồng bộ bao quanh**, chưa phải giải pháp đầy đủ. Cần xét tiếp:

- Mọi setter của **mọi** trường tham gia equality/hash phải vô hiệu hóa cache.
- Với nhiều luồng, một luồng có thể đang tính hash cũ, luồng khác đổi trạng thái và xóa cache; luồng đầu có thể ghi lại cache cũ **sau khi cache đã bị xóa**.
- Không có bảo đảm rằng một lần đọc nhiều trường mutable sẽ tạo thành một **snapshot nhất quán** nếu thiếu cùng một giao thức đồng bộ.
- Nếu đối tượng đã được chèn vào `HashMap`/`HashSet`, tính lại hash sau khi trạng thái đổi không tự chuyển vị trí phần tử trong bảng băm.

Suy ra **vô hiệu hóa cache đúng** vẫn chưa có nghĩa **đổi trạng thái khóa trong collection là an toàn**.

## 6. Nhiều luồng: `volatile` không thay thế đồng bộ trạng thái

Hãy hình dung equality của một đối tượng phụ thuộc vào hai trường mutable `name` và `revision`. Luồng A cập nhật `name` rồi cập nhật `revision`; luồng B tính hash đúng giữa hai bước đó. B có thể lấy cặp giá trị chưa phải trạng thái nghiệp vụ hoàn chỉnh. Thêm `volatile cachedHash` chỉ công bố **giá trị cache**, không biến phép đọc hai trường mutable thành một thao tác nguyên tử.

Muốn cache một hash phụ thuộc trạng thái mutable và chia sẻ nhiều luồng, cần thiết kế và kiểm chứng **toàn bộ** các quan hệ sau:

1. **Đọc/ghi trạng thái:** setter và `hashCode()` sử dụng cùng khóa đồng bộ hoặc snapshot bất biến được công bố nguyên tử.
2. **Cache gắn với phiên bản trạng thái:** không có khả năng một luồng tính từ phiên bản cũ rồi công bố sau lần invalidation của phiên bản mới.
3. **`equals()` phù hợp:** phép so sánh hai đối tượng cũng phải đọc những trạng thái logic nhất quán; nếu cần khóa hai đối tượng, phải giải quyết thứ tự khóa để tránh deadlock.
4. **Công bố đối tượng:** khởi tạo và chia sẻ instance cho luồng khác an toàn, không để trạng thái xây dựng dang dở lọt ra.
5. **Ngữ nghĩa collection:** bất kể cách đồng bộ phía trên, nếu thuộc tính xác định khóa bị sửa **trong thời gian khóa ở trong map/set**, vị trí lưu nội bộ vẫn có thể không tương ứng với giá trị hash mới.

`volatile` giải quyết visibility/order cho **một trường hoặc một bước công bố**, không tạo một transaction cho tập nhiều trường. `synchronized` chỉ có tác dụng khi mọi nơi truy cập liên quan đều tuân một giao thức đồng bộ phù hợp. `ConcurrentHashMap` bảo vệ thao tác của cấu trúc map, **không** tự bảo vệ đối tượng khóa mutable khỏi thay đổi hash/equality.

**Hướng thiết kế thường dễ chứng minh hơn:** giữ khóa bất biến, còn giá trị mutable nằm ở value của map. Ví dụ `Map<AccountKey, MutableAccountState>` dùng `AccountKey` như mục 3. Nếu cập nhật danh tính, tạo khóa mới và thực hiện thao tác thay thế phù hợp theo chính sách đồng bộ của ứng dụng. Hoặc giữ một **snapshot bất biến** mỗi lần cập nhật; mỗi snapshot có trạng thái và mã băm riêng cố định.

## 7. Kiểm tra sự khác biệt giữa bất biến và mutable khi làm khóa

Cấu trúc hash thường tính/phân phối theo hash **ở thời điểm chèn** rồi khi tra cứu sẽ tính hash của khóa truyền vào. Nếu cùng instance làm khóa nhưng giá trị tham gia hash đã đổi, việc tìm có thể đến bucket khác. Cho dù setter xóa cache đúng, dữ liệu vẫn nằm trong vị trí từ lần chèn trước đó. Việc gọi `hashCode()` chuẩn ở hiện tại không “sửa chữa” lịch sử chèn.

Vì vậy:

- `HashMap`, `HashSet` và cả `ConcurrentHashMap` đều cần khóa giữ ngữ nghĩa `equals()`/`hashCode()` ổn định **trong thời gian sử dụng làm khóa**.
- Không được suy luận rằng dùng `Collections.synchronizedMap(...)` làm việc thay đổi khóa trở nên an toàn.
- Nếu buộc phải chuyển định danh, thiết kế một thao tác cập nhật có kiểm soát: loại khóa cũ trong trạng thái cũ, tạo hoặc chọn khóa mới bất biến, chèn lại vào collection theo giao thức đồng bộ phù hợp. Không nên đổi trường hash của khóa đang lưu rồi hy vọng `remove()` tìm đúng đối tượng.
- Nếu đối tượng mutable chỉ đóng vai trò value trong map, thay đổi value không gây ra chính vấn đề bucket theo khóa, dù an toàn luồng của value vẫn phải được thiết kế riêng.

## 8. Quy trình quyết định cache `hashCode()` trong dự án

**Bước 1: Xác định dữ liệu equality.** Nếu chỉ `id` là danh tính, hash nên dựa trên `id`, không đưa thêm tên hoặc timestamp có thể đổi. Nếu là value object, cần xét những thành phần thật sự mang ý nghĩa giá trị.

**Bước 2: Kiểm tra khả năng thay đổi sâu.** Các field dùng để tính hash có bất biến thật không? Có array, list, object con hoặc reference mutable không? Có `this` thoát khỏi constructor không? Subclass có thể đổi định nghĩa equality không?

**Bước 3: Đo chi phí.** Chạy benchmark/profile với workload thực tế. Hash đơn giản đôi khi rẻ hơn việc duy trì cache; ghi thêm trường có thể làm tăng bộ nhớ cho số lượng object lớn.

**Bước 4: Chọn cách lưu nếu phù hợp.** Với object bất biến và hash thường dùng, ưu tiên tính sớm trong trường `final`. Với object bất biến và hash đắt nhưng hiếm dùng, cân nhắc tính lười cùng cơ chế công bố rõ ràng. Nếu phép hash rất rẻ, cứ tính trực tiếp.

**Bước 5: Nếu mutable, thận trọng với invalidation và concurrency.** Mọi đường ghi liên quan phải phối hợp với cache và các đường đọc, tránh ghi trả lại kết quả từ phiên bản cũ sau invalidation. Trong phần lớn ứng dụng, tách khóa bất biến đơn giản và ít lỗi hơn.

**Bước 6: Kiểm tra tập và map.** Đối tượng có được dùng làm khóa trong suốt thời gian nó có thể đổi trường equality/hash không? Nếu có, hãy thay đổi thiết kế khóa thay vì chỉ đổi cách lưu cache.

**Bước 7: Kiểm thử trường hợp biên.** Bao gồm hai instance bằng nhau, va chạm hash, hash bằng 0, cache sau cập nhật trạng thái, nhiều luồng tính đồng thời, và quan hệ `equals()`/`hashCode()` của các lớp kế thừa nếu có.

## 9. Các ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Tính hash một lần rồi lưu là tối ưu vô hại.” | Lợi ích phụ thuộc workload; cache có chi phí, và có thể sai nếu trạng thái đổi. |
| “Có `final` field nghĩa là mọi dữ liệu bên trong đều bất biến.” | `final` cố định tham chiếu, không ngăn sửa nội dung object được trỏ tới. |
| “`volatile cachedHash` biến object thành thread-safe.” | Nó chỉ bảo vệ công bố/visibility của cache theo mô hình bộ nhớ. |
| “Nếu setter xóa cache là khóa `HashMap` luôn đúng.” | Bucket lưu từ lúc chèn không tự được cập nhật theo hash mới. |
| “`ConcurrentHashMap` giải quyết khóa mutable.” | Thread safety của map không làm cho hash/equality của khóa trở nên ổn định. |
| “Hash bằng 0 tức là chưa tính.” | 0 là mã hash hợp lệ; cần cờ hoặc sentinel phù hợp nếu cần cache cả 0. |
| “Hai mã hash bằng nhau chứng minh hai object bằng nhau.” | Va chạm hash hợp lệ; vẫn cần `equals()`. |
| “Đã đặt `synchronized` trên `hashCode()` thì mọi vấn đề hết.” | Nếu trạng thái và equals không dùng cùng cơ chế phù hợp, vẫn có thể đọc dữ liệu không nhất quán. |

## 10. Checklist code review

- [ ] `equals()` và `hashCode()` dùng dữ liệu phù hợp; các object bằng nhau luôn có cùng hash.
- [ ] Thuộc tính xác định hash ổn định hoặc mọi thay đổi được phối hợp với invalidation đúng cách.
- [ ] Không nhầm `final` reference với bất biến sâu.
- [ ] Cache tính sớm được khởi tạo hoàn chỉnh trước khi object được công bố.
- [ ] Cache tính lười có cơ chế visibility thích hợp, xử lý giá trị hash bằng 0 và xét việc tính trùng.
- [ ] Khi nhiều luồng truy cập, nhất quán cho dữ liệu gốc, cache và `equals()`, không chỉ cho một trường.
- [ ] Các khóa trong `HashMap`/`HashSet` không đổi những trường làm nên equality/hash trong thời gian lưu.
- [ ] Việc lưu hash có lợi ích hiệu năng đã được đo và không làm mã khó bảo trì vô ích.

**Nguyên tắc cần nhớ:** chỉ cache `hashCode()` khi **trạng thái được băm đủ ổn định** và **cơ chế công bố/đồng bộ cho phép tái sử dụng an toàn**. Nếu chưa có lời giải rõ cho hai điều đó, hãy giữ cách tính hash trực tiếp hoặc chọn đối tượng khóa bất biến.
