# Phân biệt kiểm thử tính đúng với đánh giá phân bố hoặc hiệu năng băm

Khi viết `equals()` và `hashCode()` trong Java, có hai câu hỏi khác nhau:

1. **Tính đúng:** hai đối tượng được coi là bằng nhau có tuân thủ hợp đồng của `equals()` và `hashCode()` không? `HashSet`/`HashMap` có tra cứu được key tương đương đúng cách không?
2. **Phân bố và hiệu năng:** mã băm có trải các key của một tập dữ liệu thực tế tương đối đều không? Số va chạm, thời gian tra cứu/chèn/xóa, chi phí tính hash và bộ nhớ ra sao?

**Một hàm băm hợp lệ chưa chắc phân bố tốt; một hàm băm có phân bố trông đẹp chưa chắc đúng hợp đồng.** Kiểm thử tính đúng là điều kiện bắt buộc trước khi tối ưu hiệu năng.

## 1. Hai loại đánh giá đo những thứ khác nhau

| Khía cạnh | Kiểm thử tính đúng (correctness) | Đánh giá phân bố/hiệu năng |
| --- | --- | --- |
| Câu hỏi | Quan hệ bằng nhau và hash có tuân thủ hợp đồng Java? | Hash trải key ra sao; các thao tác trên collection có nhanh không? |
| Đơn vị kiểm tra | Đối tượng, cặp/nhóm đối tượng, hành vi tra cứu theo key | Tập dữ liệu đủ lớn, nhóm bucket mô phỏng, workload đo thời gian |
| Kết quả | PASS/FAIL, có phản ví dụ rõ ràng | Số liệu định lượng phụ thuộc dữ liệu, kích thước và môi trường |
| Tiêu chí cốt lõi | `a.equals(b) ⇒ a.hashCode() == b.hashCode()` | Tỷ lệ bucket trống, tải mỗi bucket, va chạm, throughput, độ trễ |
| Va chạm hash | **Được phép** với hai đối tượng không bằng nhau | Nhiều va chạm có thể làm giảm hiệu năng |
| Công cụ | Unit/property-based tests, assertion, `HashSet`/`HashMap` | Phân tích histogram; benchmark có warmup và kiểm soát workload, thường bằng JMH |
| Lỗi điển hình | Key bằng nhau nhưng có hash khác nhau; `equals()` bất đối xứng | Tất cả key vào một bucket; tạo hash quá tốn CPU |

Một giá trị `hashCode()` là `int` 32 bit nên không thể có mã riêng cho mọi đối tượng có thể tồn tại. Va chạm là bình thường. Hợp đồng không yêu cầu hai key khác nhau phải sinh hai mã băm khác nhau.

## 2. Hợp đồng nào phải được kiểm thử?

### 2.1. Hợp đồng `equals()`

Với những tham chiếu không `null`, `equals()` phải thể hiện quan hệ tương đương:

- **Phản xạ:** `x.equals(x)` là `true`.
- **Đối xứng:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
- **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` đều đúng thì `x.equals(z)` phải đúng.
- **Nhất quán:** các lời gọi lặp lại cho cùng hai đối tượng phải cho cùng kết quả khi thông tin dùng để so sánh không thay đổi.
- **Với null:** `x.equals(null)` là `false`.

Đối với một kiểu dữ liệu theo giá trị, cần quyết định rõ **trường nào xác định bằng nhau**. Ví dụ, với `UserKey(tenantId, userId)`, nếu cả hai trường cùng tham gia `equals()`, thì `hashCode()` phải tương thích với chính tiêu chí đó.

### 2.2. Hợp đồng `hashCode()`

- **Điều kiện bắt buộc:** nếu `x.equals(y)` thì `x.hashCode() == y.hashCode()`.
- **Nhất quán theo trạng thái:** khi các thuộc tính dùng trong `equals()` chưa thay đổi, các lần gọi `hashCode()` trong một lần chạy Java phải cho cùng giá trị.
- **Không yêu cầu chiều ngược lại:** `x.hashCode() == y.hashCode()` **không** suy ra `x.equals(y)`. Hai đối tượng không bằng nhau được phép va chạm.

Viết gọn quan hệ cần kiểm tra:

```text
equals(x, y) == true  =>  hash(x) == hash(y)      BẮT BUỘC
hash(x) == hash(y)    =>  equals(x, y) == true    KHÔNG ĐÚNG TỔNG QUÁT
equals(x, y) == false =>  hash(x) != hash(y)      KHÔNG BẮT BUỘC
```

Nếu override `equals()` để thay đổi khái niệm bằng nhau thì thông thường cũng phải override `hashCode()` tương ứng. Không viết một bài test sai như `assertNotEquals(a.hashCode(), b.hashCode())` chỉ vì `a` và `b` khác nhau: phép kiểm này không nằm trong hợp đồng.

### 2.3. Kiểm chứng ngữ nghĩa trong collection

Đối với hai instance khác nhau nhưng bằng nhau theo `equals()`, cần thử ít nhất:

- Thêm `a` vào `HashSet`, sau đó `contains(b)` phải đúng, và `add(b)` không làm số phần tử tăng.
- Gán `map.put(a, value)` thì `map.get(b)` phải trả đúng value; gán tiếp một key tương đương phải cập nhật entry tương ứng.
- Một key không tương đương không được bị coi nhầm là cùng key do `equals()` quá rộng. **Va chạm hash tự nó không làm `HashMap` gộp hai key không bằng nhau**: collection còn đối chiếu bằng `equals()`.

Những kiểm thử này bổ sung cho kiểm tra hợp đồng trực tiếp. Chúng không thay thế việc xét đối xứng, bắc cầu và các biên kiểu dữ liệu.

## 3. Ví dụ Java 17+ chạy được: đúng hợp đồng nhưng phân bố rất kém

Chương trình bên dưới có ba kiểu key:

- `GoodKey`: so sánh theo `id`; hash theo `id`. Tập ID liên tiếp trong ví dụ trải đều trên mô hình 16 bucket.
- `ConstantHashKey`: cũng so sánh theo `id`, nhưng mọi instance đều có hash bằng 7. **Hợp đồng vẫn đúng**, song tất cả phần tử va chạm.
- `BrokenKey`: so sánh chỉ theo `id`, trong khi hash trả về `salt`; hai key bằng nhau có thể mang hash khác nhau. **Vi phạm hợp đồng**, bất kể phân bố có vẻ tốt đến đâu.

Lưu thành tệp **`HashCorrectnessVsDistribution.java`**:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class HashCorrectnessVsDistribution {
    record GoodKey(int id) {
        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    record ConstantHashKey(int id) {
        @Override
        public int hashCode() {
            return 7;
        }
    }

    static final class BrokenKey {
        final int id;
        final int salt;

        BrokenKey(int id, int salt) {
            this.id = id;
            this.salt = salt;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BrokenKey key && id == key.id;
        }

        @Override
        public int hashCode() {
            return salt; // SAI: salt không tham gia equals().
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static int occupied(int[] counts) {
        int result = 0;
        for (int count : counts) {
            if (count > 0) {
                result++;
            }
        }
        return result;
    }

    static int maxLoad(int[] counts) {
        int max = 0;
        for (int count : counts) {
            max = Math.max(max, count);
        }
        return max;
    }

    static void checkGoodKeyContract() {
        GoodKey a = new GoodKey(42);
        GoodKey b = new GoodKey(42);
        GoodKey c = new GoodKey(42);
        GoodKey distinct = new GoodKey(99);

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(a.equals(b) && b.equals(c) && a.equals(c),
                "transitive");
        check(!a.equals(null), "null");
        check(!a.equals(distinct), "different ids");
        check(a.hashCode() == b.hashCode(), "hash agreement");

        Set<GoodKey> set = new HashSet<>();
        check(set.add(a), "first insert");
        check(set.contains(b), "lookup equal key");
        check(!set.add(b) && set.size() == 1, "no duplicate");

        Map<GoodKey, String> map = new HashMap<>();
        map.put(a, "found");
        check("found".equals(map.get(b)), "map lookup");
        System.out.println("GoodKey contract: PASS");
    }

    static void checkConstantHashContract() {
        ConstantHashKey a = new ConstantHashKey(42);
        ConstantHashKey b = new ConstantHashKey(42);
        check(a.equals(b), "equal ids");
        check(a.hashCode() == b.hashCode(), "same hash");

        Set<ConstantHashKey> set = new HashSet<>();
        for (int i = 0; i < 64; i++) {
            check(set.add(new ConstantHashKey(i)), "distinct ids");
        }
        check(set.size() == 64, "collision is not equality");
        check(set.contains(new ConstantHashKey(42)),
                "lookup despite collisions");
        System.out.println("ConstantHashKey contract: PASS");
    }

    static void showBrokenContract() {
        BrokenKey a = new BrokenKey(42, 1);
        BrokenKey b = new BrokenKey(42, 2);

        check(a.equals(b) && b.equals(a), "equal ids");
        check(a.hashCode() != b.hashCode(), "different salts");
        System.out.println(
                "BrokenKey: equal=true, hashesEqual=false -> VIOLATION");
    }

    static void showBucketModel() {
        int[] good = new int[16];
        int[] constant = new int[16];

        for (int id = 0; id < 64; id++) {
            int h1 = new GoodKey(id).hashCode();
            int h2 = new ConstantHashKey(id).hashCode();
            good[Math.floorMod(h1, good.length)]++;
            constant[Math.floorMod(h2, constant.length)]++;
        }

        System.out.println("Model 64 keys / 16 buckets:");
        System.out.println("GoodKey used=" + occupied(good)
                + ", max=" + maxLoad(good));
        System.out.println("ConstantHashKey used=" + occupied(constant)
                + ", max=" + maxLoad(constant));
    }

    public static void main(String[] args) {
        checkGoodKeyContract();
        checkConstantHashContract();
        showBrokenContract();
        showBucketModel();
    }
}
```

Lệnh chạy:

```bash
javac HashCorrectnessVsDistribution.java
java HashCorrectnessVsDistribution
```

Kết quả:

```text
GoodKey contract: PASS
ConstantHashKey contract: PASS
BrokenKey: equal=true, hashesEqual=false -> VIOLATION
Model 64 keys / 16 buckets:
GoodKey used=16, max=4
ConstantHashKey used=1, max=64
```

**Vì sao đây là ví dụ đáng chú ý?**

1. `ConstantHashKey` cho kết quả PASS: 64 key khác nhau vẫn được lưu riêng trong `HashSet`, và có thể tìm theo một instance key tương đương vừa tạo mới. Collisions làm collection phải phân biệt key bằng `equals()`, nên không tự gây sai kết quả.
2. Trên **mô hình minh họa** 16 bucket, `GoodKey` với id 0–63 lấp 16 bucket, mỗi bucket 4 phần tử. `ConstantHashKey` dồn cả 64 phần tử vào một bucket. Đây là sự khác biệt về phân bố, không phải hợp đồng.
3. `BrokenKey(42,1)` và `BrokenKey(42,2)` bằng nhau theo `equals()` nhưng có hash lần lượt bằng 1 và 2, nên sai điều kiện bắt buộc. Không cần đo thời gian hoặc dựa vào hành vi ngẫu nhiên của `HashMap` để chứng minh vi phạm.
4. Phép `Math.floorMod(hash,16)` ở đây là một **mô hình chia bucket đơn giản**, **không phải mô tả chính xác cách `HashMap` Java 17 trộn bit, tính chỉ số bucket, resize hoặc xử lý collision**. Không dùng các con số của mô hình làm benchmark `HashMap`.

Bởi vậy, một báo cáo kiểm thử có thể ghi đồng thời: “hợp đồng PASS, chất lượng phân bố trên workload này kém”. Hai kết luận không mâu thuẫn.

## 4. Thiết kế bộ kiểm thử correctness có sức phát hiện lỗi

### 4.1. Chọn dữ liệu có chủ đích

Đừng chỉ tạo 100 đối tượng ngẫu nhiên rồi xác nhận không có exception. Hãy chuẩn bị nhóm đối tượng đúng theo **ngữ nghĩa bình đẳng** mà lớp khai báo:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Cùng một reference `a` | `a.equals(a)` đúng |
| Hai instance độc lập nhưng cùng tập trường định danh | `equals()` đúng và hash giống nhau |
| Khác đúng một trường **có** tham gia `equals()` | Thường `equals()` sai theo quy tắc lớp |
| Khác trường **không** tham gia `equals()` | `equals()` không được thay đổi chỉ vì trường này |
| Đối tượng khác kiểu, lớp cha/con nếu có kế thừa | Không phá đối xứng hoặc bắc cầu |
| Giá trị `null`, rỗng, Unicode, số âm, biên số nguyên | Không sai hành vi hoặc ném lỗi ngoài dự kiến |
| Tạo nhiều instance có cùng dữ liệu, rồi sử dụng làm key | Set/map vẫn tìm được key tương đương |
| Các key khác nhau nhưng hash trùng | Set/map vẫn giữ chúng là các key riêng nếu không `equals()` |

Nếu `equals()` phụ thuộc mảng, chú ý `array.equals(otherArray)` mặc định dùng danh tính mảng, còn `Arrays.equals`/`Arrays.deepEquals` so sánh nội dung theo cách riêng. Quy tắc so sánh và băm phải tương thích, ví dụ `Arrays.equals` đi cùng `Arrays.hashCode` với mảng một chiều thích hợp.

Nếu key sử dụng `double`, `BigDecimal`, hoặc lớp có quy tắc bằng nhau đặc biệt, hãy thử NaN, giá trị `-0.0`/`0.0`, hay scale khác nhau khi chúng có liên quan đến tiêu chí equals của kiểu cụ thể. Không giả định tất cả kiểu số có chung một định nghĩa “bằng nhau”.

### 4.2. Property-based test và quy tắc khi sinh dữ liệu

Với một bộ sinh đối tượng, có thể kiểm tra nhiều bộ ba `(a,b,c)` để tìm phản ví dụ về đối xứng/bắc cầu. Tuy nhiên, random thuần thường hiếm khi tạo ra hai instance bằng nhau. Cần **chủ động sao chép cùng khóa ngữ nghĩa**, sinh biến thể khác một trường định danh, và sinh biến thể khác trường không tham gia `equals()`.

Pseudo-code kiểm tra cặp:

```text
for each pair (a, b):
    assert a.equals(b) == b.equals(a)
    if a.equals(b):
        assert a.hashCode() == b.hashCode()
    // Không assert hash khác nhau khi equals false.

for each triple (a, b, c):
    if a.equals(b) and b.equals(c):
        assert a.equals(c)
```

Thêm kiểm tra `equals(null)`, phản xạ, việc gọi lặp lại khi trạng thái không đổi, và hành vi thực tế của map/set. Nếu sinh nhiều dữ liệu, hãy lưu seed và phản ví dụ tối giản để lỗi tái hiện được.

**Giới hạn bằng chứng:** test chạy hết các trường hợp đã chọn chỉ chứng minh hành vi trong miền kiểm thử. Nó không chứng minh tuyệt đối mọi quan hệ bằng nhau hợp lệ với mọi giá trị có thể có. Sự chính xác của định nghĩa `equals()` vẫn cần được xem xét ở mức thiết kế.

### 4.3. Bẫy key mutable

Ngay cả khi `equals()`/`hashCode()` được viết nhất quán ở từng thời điểm, thay đổi trường tham gia phép bằng nhau sau khi đưa instance vào `HashSet` hay làm key `HashMap` có thể khiến việc tìm kiếm thất bại: key đã nằm ở vị trí dựa vào hash cũ. Bài test nên bảo đảm một trong hai quy tắc thiết kế:

- Ưu tiên key bất biến, chẳng hạn `record` với các thành phần phù hợp và không để lộ trạng thái mutable ảnh hưởng tới phép so sánh.
- Hoặc bảo đảm ứng dụng không sửa trạng thái tham gia equality/hash trong suốt thời gian key đang nằm trong cấu trúc băm; muốn đổi key thì xóa rồi thêm lại một cách có kiểm soát.

Với một `record`, các thành phần reference tới danh sách/mảng có thể vẫn trỏ tới dữ liệu mutable. `record` không tự động làm toàn bộ đồ thị đối tượng bên trong trở nên bất biến.

## 5. Đánh giá phân bố băm: đo đúng đối tượng và dữ liệu

Sau khi correctness PASS, đánh giá chất lượng hash trên **tập key thực sự dự kiến sử dụng**. Một hàm hash có phân bố tốt trên các ID liên tiếp có thể không tốt trên các ID có cấu trúc đặc biệt, chẳng hạn phần thấp luôn bằng 0; tương tự một benchmark trên vài chục key không đại diện cho hệ thống hàng triệu key.

Có thể làm một thí nghiệm bucket mô phỏng theo các bước:

1. Tạo dữ liệu đầu vào có ý nghĩa: ID liên tiếp, ID tăng theo bước cố định, chuỗi với tiền tố chung, dữ liệu ngẫu nhiên được lưu seed, và phân bố key gần giống thực tế.
2. Chọn số bucket cho mô hình và quy tắc ánh xạ `hash → bucket`, công bố rõ quy tắc ấy. Phân biệt mô hình với nội bộ `HashMap`.
3. Đếm số phần tử trong mỗi bucket; tính số bucket có ít nhất một key, tải trung bình `N / B`, tải lớn nhất và histogram tải bucket.
4. Tính số va chạm **theo định nghĩa đang dùng**, chẳng hạn số phần tử vượt phần tử đầu trong mỗi bucket `sum(max(0, bucketSize - 1))`. Không đánh đồng “mã hash trùng nhau” với “rơi cùng bucket sau ánh xạ”.
5. Lặp lại ở nhiều kích thước và kiểu dữ liệu; so sánh với cùng một tập key, cùng cách ánh xạ và cùng số bucket.

Ví dụ khi có 64 key, 16 bucket:

- `GoodKey` trong chương trình: 16 bucket có dữ liệu, tải trung bình 4, tải lớn nhất 4; số phần tử vượt vị trí đầu theo định nghĩa trên là `64 - 16 = 48`.
- `ConstantHashKey`: 1 bucket có dữ liệu, tải trung bình trên toàn bộ 16 bucket vẫn là 4 nhưng tải lớn nhất 64; số phần tử vượt vị trí đầu là `64 - 1 = 63`.

**Tải trung bình giống nhau không đồng nghĩa phân bố giống nhau.** Cần xem histogram/độ lệch/tải cực đại. Một mã hash `int` phân bố khá đều vẫn có collision bucket vì số bucket nhỏ hơn không gian hash và số phần tử.

Nếu muốn kiểm tra `HashMap`/ `HashSet` thực tế, chỉ số bucket đơn giản không đủ. Cấu trúc bảng, dung lượng, hệ số tải, phép trộn bit và xử lý va chạm phụ thuộc triển khai và phiên bản JDK. Không truy cập các chi tiết nội bộ chưa được bảo đảm rồi coi đó là hợp đồng API Java.

## 6. Đo hiệu năng collection: bài toán khác với phân bố

Một histogram tốt có thể **gợi ý** tốc độ tra cứu tốt hơn, nhưng không tự chứng minh nó. Chi phí thực tế còn có tính toán `hashCode()`, `equals()`, cấp phát, locality của bộ nhớ, kích thước bảng, thao tác insert/get/remove, GC, JIT và đặc tính dữ liệu.

Đối với `HashMap` hoặc `HashSet`, hãy xác định:

- **Workload:** chèn bao nhiêu key, tỷ lệ đọc/ghi, tỷ lệ tra cứu thành công/thất bại, số phần tử đồng thời và sự phân bố các key truy cập.
- **Đại lượng:** throughput (thao tác/giây), độ trễ mỗi thao tác, phân vị như p50/p95/p99 nếu có ý nghĩa, cùng cấp phát/GC khi cần.
- **Thiết lập:** JDK và cấu hình JVM, máy, kích thước heap, khả năng chạy cạnh các tiến trình khác, chế độ warmup, nhiều lượt/fork và khoảng biến thiên kết quả.
- **So sánh công bằng:** giữ cùng tập key, cùng semantics của `equals()`, cùng số lượng phần tử và trình tự thao tác. Nếu một phương án cho kết quả sai hợp đồng, loại phương án đó khỏi so sánh tối ưu.
- **Benchmark đáng tin:** ưu tiên JMH, thiết kế `@State`, `@Setup`, `@Benchmark` và các chế độ đo thích hợp. Tránh kết luận bằng một phép `System.nanoTime()` bao quanh một vòng lặp duy nhất.

Ví dụ một phép đo bị nhiễu là tạo `new HashMap<>()`, cấp phát hàng nghìn key, chèn key và đo tổng thời gian rồi gọi đó là “thời gian hashCode”. Nó đang trộn cả cấp phát, resize, duyệt collection và chạy bytecode/JIT; kết quả không trả lời đúng câu hỏi.

Với Java `HashMap`, trong điều kiện băm và tải phù hợp, get/put thường có thời gian kỳ vọng gần hằng số trên mỗi thao tác; va chạm nghiêm trọng có thể làm chậm đáng kể. Hành vi cụ thể của một bucket va chạm còn tùy key, thứ tự chèn, kích thước và chi tiết triển khai, nên không khẳng định một hệ số hoặc thời gian cụ thể khi chưa đo.

Một hàm hash tốn nhiều phép toán hơn nhưng phân bố tốt hơn có thể nhanh hơn hoặc chậm hơn tổng thể, tùy tần suất tra cứu và kích thước collection. **Chỉ số phân bố và benchmark phải được đọc cùng với nhau**, chứ không dùng một chỉ số thay tất cả.

## 7. Thứ tự kiểm chứng được khuyến nghị

```text
Định nghĩa semantics của key
             |
             v
Kiểm thử equals + hashCode contract
             |
       FAIL? +-- Có --> Sửa định nghĩa/triển khai rồi kiểm lại
             |
            Không
             v
Kiểm thử hành vi HashSet / HashMap
             |
             v
Phân tích phân bố trên dữ liệu đại diện
             |
             v
Đo JMH trên workload quan trọng
             |
             v
Đánh giá trade-off: độ đúng, tốc độ, bộ nhớ, độ phức tạp
```

Khi xem kết quả, diễn giải từng tình huống:

| Correctness | Phân bố/hiệu năng | Hành động |
| --- | --- | --- |
| FAIL | Bất kỳ | Sửa hợp đồng trước. Benchmark không thể hợp thức hóa key sai. |
| PASS | Tốt với workload mục tiêu | Giữ thiết kế, theo dõi khi workload thay đổi. |
| PASS | Kém trên workload thực tế | Thử hash khác nhưng phải giữ cùng semantics `equals()` và chạy lại toàn bộ correctness tests. |
| PASS | Chưa đo | Chưa đủ bằng chứng để tuyên bố hash nhanh/chậm; chỉ kết luận đúng hợp đồng trên dữ liệu kiểm thử. |

Không tối ưu để “mọi đối tượng đều có hash khác nhau”: điều này không phải yêu cầu của Java, và không khả thi cho miền key lớn hơn số lượng giá trị `int`. Mục tiêu có ý nghĩa là **đảm bảo đúng hợp đồng** và sau đó đạt hiệu năng phù hợp với dữ liệu, workload thực tế.

## 8. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Assert hai key không bằng nhau phải có hash khác nhau | Hash collision là hợp lệ | Chỉ bắt buộc hai key bằng nhau có hash bằng nhau |
| Kiểm tra histogram đẹp rồi kết luận `equals()` đúng | Phân bố không xác thực phản xạ/đối xứng/bắc cầu | Viết test hợp đồng độc lập |
| `hashCode()` luôn trả cùng hằng số nên gọi là bug chức năng | Nó có thể hoàn toàn đúng hợp đồng | Gắn nhãn rủi ro hiệu năng, kiểm tra workload |
| Mỗi lần `hashCode()` trả random để có vẻ “đều” | Không ổn định, phá hợp đồng và lookup | Hash phải ổn định khi trạng thái bằng nhau không đổi |
| Dùng key mutable rồi sửa trường định danh khi ở trong map | Tra cứu có thể thất bại dù code có vẻ đúng trước đó | Key bất biến hoặc remove/reinsert đúng quy trình |
| Benchmark một lần không warmup | JIT, GC, cấp phát và nhiễu hệ thống chi phối | Dùng JMH, thiết lập và lặp lại hợp lý |
| Đo bucket modulo rồi khẳng định số liệu nội bộ `HashMap` | Mô hình không phản ánh đầy đủ implementation | Ghi rõ đó là histogram minh họa |
| Tối ưu hash rồi bỏ qua test equality | Có thể làm mất tương thích giữa `equals` và hash | Chạy lại correctness suite sau mỗi thay đổi |
| Xem throughput một mình là mọi thứ | Có thể che độ trễ xấu, bộ nhớ hoặc GC | Đo chỉ số phù hợp mục tiêu sử dụng |

## 9. Checklist trước khi kết luận

1. Đã viết rõ **khóa nghiệp vụ** và trường nào thuộc `equals()`?
2. Đã kiểm tra phản xạ, đối xứng, bắc cầu, null, consistency, các trường hợp biên và cặp key bằng nhau theo giá trị nhưng là hai instance khác nhau?
3. Đã kiểm tra `equals ⇒ same hash`, đồng thời **không bắt** các key khác nhau phải có hash khác nhau?
4. Đã xác nhận `HashSet`/`HashMap` nhận diện và truy xuất đúng một key tương đương, kể cả khi có collision?
5. Đã xử lý nguy cơ sửa key sau khi đưa vào collection?
6. Nếu nói về chất lượng phân bố: đã xác định rõ dataset, mô hình bucket, metric và sự khác biệt với nội bộ `HashMap`?
7. Nếu nói về hiệu năng: đã có benchmark đáng tin, workload đại diện, số lần đo, môi trường, warmup và kết quả so sánh công bằng?

**Ghi nhớ:** kiểm thử `equals()`/`hashCode()` trả lời **“có đúng hay không?”**; phân tích phân bố và benchmark trả lời **“tốt đến mức nào trên dữ liệu và môi trường này?”**. Việc một hàm băm có nhiều va chạm chưa tự làm sai hợp đồng, còn một hàm băm nhìn có vẻ phân bố tốt không thể bù đắp quan hệ bằng nhau bị định nghĩa sai.
