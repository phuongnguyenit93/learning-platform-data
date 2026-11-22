# Tính ổn định của `hashCode()` trong một lần chạy khi thông tin dùng trong `equals()` không đổi

## 1. Quy tắc chính xác của hợp đồng `hashCode()`

Trong Java, phương thức `Object.hashCode()` trả về một số nguyên kiểu `int` dùng chủ yếu để hỗ trợ các cấu trúc dữ liệu dựa trên bảng băm, chẳng hạn `HashMap` và `HashSet`. Một yêu cầu cốt lõi của hợp đồng là:

> Trong một lần thực thi ứng dụng Java, nếu không có thông tin nào được dùng trong các phép so sánh `equals()` trên đối tượng bị thay đổi, thì mỗi lần gọi `hashCode()` trên đối tượng đó phải nhất quán trả về cùng một số nguyên.

Có thể diễn đạt bằng điều kiện:

```text
Nếu thông tin quyết định equals(x, ...) không đổi trong khoảng T,
thì mọi lần gọi x.hashCode() trong khoảng T phải có cùng kết quả.
```

Đây là **tính ổn định có điều kiện**, không phải lời hứa rằng mã băm không bao giờ đổi trong suốt vòng đời đối tượng.

Ví dụ với đối tượng đại diện cho khách hàng có `customerId` quyết định `equals()`:

- Nếu `customerId` không thay đổi, `hashCode()` phải giữ nguyên trong cùng lần chạy.
- Nếu `customerId` **thực sự thay đổi**, hợp đồng nhất quán nói trên không bắt buộc giá trị băm cũ phải giữ nguyên; tuy nhiên, việc thay đổi khóa sau khi đưa vào bảng băm có thể khiến tra cứu không tìm thấy.
- Nếu đổi `displayName` nhưng `equals()` **không** dùng `displayName`, thì chỉ việc đổi tên hiển thị không phải lý do hợp lệ để `hashCode()` đổi.

Cụm **“trong một lần chạy”** rất quan trọng: hợp đồng Java không yêu cầu `hashCode()` của cùng một đối tượng, hoặc cùng một giá trị tái tạo, phải cho một số nguyên giống nhau giữa các lần khởi động JVM khác nhau. Đừng lưu `hashCode()` như mã định danh bền vững trong database, URL hoặc file để sử dụng ở lần chạy sau.

## 2. Quan hệ với `equals()`

Tính ổn định chỉ là **một** phần của hợp đồng `hashCode()`. Phần còn lại liên quan trực tiếp đến `equals()`:

1. **Nhất quán theo thời gian có điều kiện:** nếu thông tin dùng để so sánh bằng nhau không đổi, nhiều lần gọi `x.hashCode()` trong cùng lần chạy phải cho cùng số nguyên.
2. **Các đối tượng bằng nhau phải có cùng mã băm:** nếu `x.equals(y)` là `true`, thì `x.hashCode() == y.hashCode()` phải là `true`.
3. **Các đối tượng không bằng nhau được phép trùng mã băm:** khi `x.equals(y)` là `false`, hai mã băm có thể khác **hoặc giống nhau**. Trùng mã băm là *collision*, không tự nó vi phạm hợp đồng.

Ví dụ: `hashCode()` luôn trả về `7` là ổn định và bảo đảm các đối tượng bằng nhau có cùng mã băm. Nhưng cách này làm mọi đối tượng rơi vào cùng giá trị băm, có thể khiến bảng băm kém hiệu quả. Vì vậy cần phân biệt **đúng hợp đồng** với **chất lượng phân bố mã băm**.

Một lớp override `equals()` theo giá trị thì phải override `hashCode()` bằng những thông tin phù hợp với tiêu chí bình đẳng ấy. Tránh dùng `System.identityHashCode(this)` khi `equals()` đã định nghĩa hai đối tượng *khác tham chiếu* là bằng nhau: mã băm danh tính không bảo đảm bằng nhau cho hai đối tượng cùng giá trị.

## 3. `hashCode()` ổn định phụ thuộc vào những gì?

Xét lớp `AccountKey` có `tenantId`, `accountId` và `description`:

- Nếu `equals()` chỉ so sánh `tenantId` và `accountId`, đây là các thông tin xác định bình đẳng.
- Một cách cài đặt `hashCode()` phù hợp là tính từ **cùng bộ khóa logic** `tenantId` và `accountId`.
- `description` được dùng để hiển thị, không tham gia `equals()`; thay đổi nó không được làm mã băm của khóa thay đổi nếu thông tin bình đẳng vẫn như cũ.

“Dùng cùng bộ khóa logic” là nguyên tắc thiết kế thực tế, không phải yêu cầu rằng công thức trong `hashCode()` phải gọi đúng từng getter mà `equals()` gọi. Điều bắt buộc là **bất kỳ hai đối tượng được `equals()` xem là bằng nhau đều có cùng mã băm**, và điều kiện ổn định ở mục 1 được bảo toàn.

Hợp đồng không yêu cầu kết quả băm có tính ngẫu nhiên, phải dương, duy nhất, hoặc phản ánh địa chỉ bộ nhớ. `int` âm, `0` hay collision đều hợp lệ.

## 4. Ví dụ chạy được với Java 17

Chương trình sau minh họa ba trường hợp có tính chất khác nhau:

- `StableKey`: tiêu chí bình đẳng bất biến, mã băm ổn định.
- `BrokenHashKey`: dữ liệu bình đẳng không đổi nhưng mỗi lần băm lại trả về một số khác, **vi phạm hợp đồng**.
- `MutableKey`: công thức `equals()`/`hashCode()` nhất quán, nhưng trường thuộc khóa bị sửa sau khi đưa vào `HashMap`; đây là rủi ro của **khóa mutable**, và tính ổn định có điều kiện không còn được bảo đảm sau khi sửa trường khóa.

Lưu thành tệp **`HashCodeStabilityDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class HashCodeStabilityDemo {
    static final class StableKey {
        private final String id;

        StableKey(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof StableKey that
                    && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    static final class BrokenHashKey {
        private final String id;
        private int hashCalls;

        BrokenHashKey(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof BrokenHashKey that
                    && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return ++hashCalls; // SAI: mã băm tùy số lần gọi.
        }
    }

    static final class MutableKey {
        private String id;

        MutableKey(String id) {
            this.id = Objects.requireNonNull(id);
        }

        void setId(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof MutableKey that
                    && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        StableKey first = new StableKey("A");
        StableKey second = new StableKey("A");
        System.out.println("stable hash #1: " + first.hashCode());
        System.out.println("stable hash #2: " + first.hashCode());
        System.out.println("equal objects: " + first.equals(second));
        System.out.println("equal hashes: "
                + (first.hashCode() == second.hashCode()));

        BrokenHashKey broken = new BrokenHashKey("A");
        System.out.println("broken hash #1: " + broken.hashCode());
        System.out.println("broken hash #2: " + broken.hashCode());

        Map<BrokenHashKey, String> badMap = new HashMap<>();
        badMap.put(broken, "value");
        System.out.println("broken map get: " + badMap.get(broken));

        MutableKey mutable = new MutableKey("A");
        Map<MutableKey, String> mutableMap = new HashMap<>();
        mutableMap.put(mutable, "saved");
        System.out.println("mutable before: " + mutableMap.get(mutable));
        mutable.setId("B");
        System.out.println("mutable after: " + mutableMap.get(mutable));
        System.out.println("mutable hash after: " + mutable.hashCode());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 HashCodeStabilityDemo.java
java HashCodeStabilityDemo
```

Kết quả:

```text
stable hash #1: 65
stable hash #2: 65
equal objects: true
equal hashes: true
broken hash #1: 1
broken hash #2: 2
broken map get: null
mutable before: saved
mutable after: null
mutable hash after: 66
```

**Giải thích kết quả:**

1. `String.hashCode()` của `"A"` bằng `65` và `"B"` bằng `66`. `StableKey` giữ `id` dưới dạng `final String`, nên dữ liệu quyết định bình đẳng không thay đổi; hai lần gọi `first.hashCode()` đều trả `65`. Hai đối tượng `StableKey("A")` khác tham chiếu nhưng bằng nhau và có mã băm bằng nhau.
2. `BrokenHashKey.hashCode()` trả `1`, rồi `2` dù `id` chưa từng thay đổi. Đây là **vi phạm rõ ràng** quy tắc ổn định. Khi `HashMap.put` gọi `hashCode()`, bộ đếm tăng lên `3`; `get` tăng lên `4`. Giá trị băm dùng cho việc tìm khác giá trị băm đã lưu lúc thêm khóa, nên ví dụ không tìm thấy entry.
3. `MutableKey("A")` được thêm vào bản đồ với mã băm `65` và truy xuất được. Sau khi `setId("B")`, mã băm mới là `66`; `HashMap` không tự di chuyển entry đã được lưu sang nhóm băm mới. Vì vậy `get(mutable)` trả `null`. **Lỗi sử dụng là sửa khóa khi nó đang nằm trong bản đồ**, còn bản thân công thức băm `id.hashCode()` vẫn nhất quán với các trường dùng trong `equals()` ở từng trạng thái.
4. Ví dụ sử dụng `HashMap` mặc định của Java 17 với các giá trị `65` và `66`, nên các thao tác tra cứu nêu trên có kết quả xác định. Điều quan trọng về nguyên lý không phải giá trị số cụ thể, mà là mã băm khác nhau khiến quá trình tra cứu đến vị trí khác.

Lưu ý: hai lớp có tên `BrokenHashKey` và `MutableKey` được viết **để minh họa lỗi và rủi ro**, không nên sao chép như khóa dùng trong ứng dụng.

## 5. Tại sao việc đổi mã băm làm `HashMap` và `HashSet` khó sử dụng?

Tại thời điểm `put(key, value)`, `HashMap` lấy mã băm của khóa để định vị nơi lưu entry. `get(key)` lại lấy mã băm hiện tại để tìm vị trí cần tra cứu, sau đó so sánh khóa khi cần thiết. `HashSet` sử dụng cơ chế bảng băm tương tự để quản lý phần tử.

Vì vậy một khóa có mã băm thay đổi trong khi vẫn nằm trong bảng băm có thể gây ra:

- `map.get(key)` trả về `null` dù bạn vừa thêm chính đối tượng ấy.
- `map.containsKey(key)`, `set.contains(key)` hoặc `set.remove(key)` thất bại ngoài dự kiến.
- Một khóa tương đương có thể không tìm được entry cũ nếu `equals()`/`hashCode()` của nó hoặc khóa đã lưu không còn cùng cách diễn giải.
- Dữ liệu vẫn có thể hiện diện khi duyệt các entry nhưng không tìm thấy bằng thao tác tra cứu thông thường.

Không phải **mọi** thay đổi giá trị băm đều khiến lookup thất bại trong mọi cấu hình: bucket, collision và cơ chế nội bộ có thể tác động đến kết quả. Thiết kế đúng không được phụ thuộc vào việc một tình huống tình cờ còn tra cứu được. Hãy giữ nguyên các thuộc tính dùng làm khóa trong toàn bộ thời gian đối tượng nằm trong cấu trúc băm.

Việc `equals()` trả về `true` khi một đối tượng được so với chính nó cũng không cứu được khóa có mã băm sai: quá trình `HashMap` có thể không tới bước so sánh `equals()` nếu mã băm hiện tại khác mã băm entry đã lưu.

## 6. Trường hợp nào mã băm có thể thay đổi mà không tự động vi phạm hợp đồng?

Hợp đồng nói rõ **“nếu không có thông tin dùng trong `equals()` bị sửa”**. Ví dụ:

```java
final class Task {
    private String taskCode;

    Task(String taskCode) {
        this.taskCode = taskCode;
    }

    void changeTaskCode(String newCode) {
        this.taskCode = newCode;
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || other instanceof Task that
                        && Objects.equals(taskCode, that.taskCode);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(taskCode);
    }
}
```

Đây là **mảnh code minh họa**, cần `import java.util.Objects;` khi đặt vào tệp Java. Khi `taskCode` được thay đổi, thông tin quyết định `equals()` đã thay đổi. Do đó mã băm đổi theo không tự động vi phạm điều khoản ổn định có điều kiện. Tuy nhiên, tránh sửa `taskCode` nếu `Task` đang được dùng làm khóa `HashMap` hoặc phần tử `HashSet`.

Ngược lại, nếu lớp còn trường `lastViewedAt` **không tham gia `equals()`**, `hashCode()` không nên sử dụng giá trị trường ấy để thay đổi mã băm. Làm vậy có thể vi phạm cả tính ổn định lẫn quy tắc các đối tượng bằng nhau phải có cùng mã băm.

Có thể lựa chọn thiết kế đối tượng mutable nhưng **cố định khóa logic**: các thuộc tính hiển thị được phép sửa, trong khi những trường dùng cho `equals()` và `hashCode()` được giữ bất biến.

## 7. Những cách cài đặt dễ phá vỡ tính ổn định

### 7.1. Gọi thời gian thực, random hoặc biến đếm trong `hashCode()`

Các cách viết như:

```java
@Override
public int hashCode() {
    return (int) System.currentTimeMillis(); // SAI
}
```

hoặc:

```java
@Override
public int hashCode() {
    return ++counter; // SAI nếu counter không phải dữ liệu equals thay đổi có chủ đích
}
```

đều không thích hợp cho mã băm của đối tượng khi thông tin bình đẳng giữ nguyên. Đây là các **mảnh mã lỗi minh họa**, không phải chương trình độc lập.

Ngay cả khi hai lần gọi có thể tình cờ trả cùng một giá trị, tính ngẫu nhiên hoặc thời gian không bảo đảm sự nhất quán cần có. Tránh truy vấn trạng thái cấu hình, dữ liệu bên ngoài hoặc dịch vụ mạng để tính băm nếu chúng không phải giá trị danh tính ổn định của đối tượng.

### 7.2. Tính băm từ nhiều trường hơn `equals()`

Giả sử `equals()` coi hai sản phẩm có cùng `sku` là bằng nhau, nhưng `hashCode()` dùng cả `sku` và `price`. Hai đối tượng cùng `sku` nhưng khác `price` có thể có hai mã băm khác nhau, vi phạm quy tắc **bằng nhau thì cùng băm**. Ngoài ra, khi `price` thay đổi, băm có thể đổi dù thông tin dùng cho `equals()` giữ nguyên.

Cách sửa: dùng cùng tiêu chí danh tính logic ở hai phương thức; nếu `price` không quyết định `equals()`, loại nó khỏi công thức `hashCode()`.

### 7.3. Trường là mảng hoặc collection mutable

Khai báo `final int[] values` chỉ cố định **tham chiếu tới mảng**, không khiến các phần tử bên trong bất biến. Khi sử dụng `Arrays.equals(values, other.values)` cùng `Arrays.hashCode(values)`, sửa phần tử sau khi thêm khóa vào `HashMap` vẫn có thể đổi mã băm.

Với collection mutable cũng tương tự: các thay đổi phần tử có thể thay đổi `equals()`/`hashCode()`. Cân nhắc sao chép phòng vệ, kiểu bất biến, hoặc giữ danh tính theo một mã ID bất biến.

Đặc biệt, `Object.hashCode()` mặc định của mảng xét theo danh tính đối tượng mảng, còn `Arrays.hashCode(array)` tính theo nội dung. Cần chọn phương pháp phù hợp với cách so sánh bằng nhau đang dùng.

### 7.4. Cache mã băm không hợp lệ

Cache `hashCode()` là một tối ưu hóa **có điều kiện**: nó phù hợp khi các giá trị tham gia bình đẳng bất biến và phép băm được tính đúng từ chúng. Với trường có thể thay đổi, cache cũ có thể trở nên sai hoặc không khớp với `equals()` sau khi cập nhật.

Nếu chọn cache cho đối tượng có trường mutable, phải thiết kế cơ chế vô hiệu hóa cache và bảo đảm tính đúng đắn khi truy cập đồng thời; giải pháp đơn giản và ít rủi ro hơn thường là dùng immutable value object.

### 7.5. Nhầm giá trị băm với danh tính lâu dài

`hashCode()` không phải UUID, khóa database, mã bảo mật hay checksum chống giả mạo. Collision được phép xảy ra và hợp đồng không yêu cầu ổn định giữa các lần chạy. Nếu cần định danh lưu trữ, hãy dùng một ID nghiệp vụ được xác định rõ (ví dụ UUID), sau đó có thể tính `equals()`/`hashCode()` từ ID đó.

## 8. Thiết kế khuyến nghị và kiểm thử

Đối với khóa bản đồ, mô hình dễ duy trì là value object bất biến:

```java
import java.util.Objects;

public record CustomerKey(String tenantId, long customerId) {
    public CustomerKey {
        Objects.requireNonNull(tenantId);
    }
}
```

Đây là khai báo record Java 17 hợp lệ; khi đưa vào tệp `CustomerKey.java`, nó biên dịch được. Java tự tạo `equals()` và `hashCode()` phù hợp với các record component. Vì `String` và `long` đều là giá trị ổn định và các component của record không thể gán lại sau khi tạo, kiểu này là lựa chọn phù hợp làm khóa.

**Record không bảo đảm bất biến sâu:** một record chứa `List` mutable, mảng hoặc object mutable vẫn có thể chứng kiến nội dung của component bị sửa sau khi tạo. Vì vậy hãy đánh giá cả *kiểu dữ liệu của từng component*, không chỉ từ khóa `record`.

Khi review hoặc viết test cho lớp đã override `equals()`/`hashCode()`, nên kiểm tra các trường hợp sau:

1. **Lặp lại không đổi:** tạo `x`, gọi `x.hashCode()` nhiều lần khi dữ liệu dùng cho `equals()` không đổi; mọi kết quả phải giống nhau.
2. **Bằng nhau thì cùng băm:** tạo `x` và `y` khác tham chiếu nhưng `x.equals(y)` trả `true`; xác nhận `x.hashCode() == y.hashCode()`.
3. **Trường không tham gia bình đẳng:** sửa một thuộc tính được phép thay đổi nhưng không thuộc `equals()`; kết quả băm phải vẫn phù hợp hợp đồng, trong đó tính ổn định không được phá vỡ.
4. **Trường quyết định bình đẳng:** nếu kiểu cho phép sửa trường khóa, đánh giá công thức băm sau thay đổi và không dùng đối tượng làm khóa trong bảng băm khi đang sửa.
5. **Tương tác collection:** dùng một khóa cùng giá trị để `put/get` hoặc `add/contains`; xác nhận hành vi ổn định khi khóa không thay đổi.
6. **Nguồn dữ liệu bên ngoài:** tìm lời gọi đồng hồ, random, biến toàn cục, network, getter có side effect hoặc cache không an toàn trong đường tính băm.

Một phép thử nhỏ có thể viết như sau (đoạn mã nằm trong phương thức của lớp kiểm thử, không phải tệp độc lập):

```java
int expected = key.hashCode();

for (int i = 0; i < 100; i++) {
    if (key.hashCode() != expected) {
        throw new AssertionError("hashCode khong on dinh");
    }
}
```

Đảm bảo `key` khác `null` và thông tin dùng trong `equals()` không thay đổi trong quá trình thử. Phép thử lặp giúp bắt nhiều lỗi, nhưng không thể chứng minh tuyệt đối mọi nhánh tính toán hoặc tình huống đa luồng. Cần kết hợp đọc code và kiểm tra thiết kế.

## 9. Những điều cần nhớ

- `hashCode()` phải trả **cùng một số nguyên trong cùng lần chạy** khi thông tin dùng để so sánh `equals()` không đổi.
- Nếu hai đối tượng bằng nhau theo `equals()`, mã băm của chúng **phải** bằng nhau; đối tượng không bằng nhau **có thể** trùng mã băm.
- Không cần cùng mã băm qua nhiều lần chạy JVM, và mã băm không phải định danh lưu trữ lâu dài.
- Nếu thay đổi trường dùng trong `equals()`, mã băm có thể thay đổi mà không tự động vi phạm điều khoản ổn định có điều kiện. Dù vậy, **đừng sửa khóa khi nó đang nằm trong `HashMap` hoặc `HashSet`**.
- Tránh dùng thời gian hiện tại, random, số lần gọi, trường không tham gia bình đẳng hoặc dữ liệu bên ngoài biến động để quyết định mã băm.
- Ưu tiên khóa logic bất biến, thiết kế `equals()`/`hashCode()` tương ứng và kiểm thử cả tính ổn định lẫn cách collection tra cứu.
