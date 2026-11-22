# Kiểm thử hợp đồng equals–hashCode và Comparator

## 1. Vì sao collection làm lộ lỗi của đối tượng?

Một đối tượng có thể in ra đúng dữ liệu nhưng vẫn không được tìm thấy trong `HashSet`. Hai bản ghi có thể khác nhau nhưng chỉ còn một phần tử khi đưa vào `TreeSet`. Một comparator có thể sắp xếp đúng vài số nhỏ rồi sai khi gặp giá trị biên.

Các hiện tượng đó thường bắt nguồn từ quan hệ bằng nhau hoặc thứ tự mà lớp đối tượng cung cấp. Collection dựa vào những quan hệ này để tìm kiếm, loại trùng, thay thế hoặc sắp xếp.

Cần kiểm thử hai lớp yêu cầu riêng:

1. **Luật của hợp đồng Java**: phản xạ, đối xứng, bắc cầu, tính nhất quán và các quan hệ giữa kết quả.
2. **Ý nghĩa của miền bài toán**: những trường nào xác định hai bản ghi bằng nhau, ưu tiên sắp xếp nào đúng, trường hợp hòa có được gộp thành một phần tử không.

Một phép `equals` chỉ so danh tính tham chiếu vẫn có thể thỏa các luật chung, nhưng sai nếu ứng dụng yêu cầu bằng nhau theo mã và phiên bản. Tương tự, comparator chỉ so điểm có thể hợp lệ về thứ tự nhưng chưa phù hợp để phân biệt bản ghi trong `TreeSet`.

## 2. Biến hợp đồng equals thành các ca kiểm thử

Với `a`, `b`, `c` là các tham chiếu khác `null` trong miền đang xét:

| Luật | Điều cần kiểm tra | Dữ liệu cần có |
| --- | --- | --- |
| Phản xạ | `a.equals(a)` là `true` | Mỗi đối tượng mẫu |
| Đối xứng | `a.equals(b)` bằng `b.equals(a)` | Cặp bằng nhau, cặp khác nhau; chú ý kế thừa nếu được hỗ trợ |
| Bắc cầu | Nếu `a.equals(b)` và `b.equals(c)` thì `a.equals(c)` | Ba đối tượng khác tham chiếu nhưng cùng giá trị được coi là bằng nhau |
| Nhất quán | Gọi lại cho cùng kết quả khi thông tin liên quan không đổi | Giữ nguyên trạng thái trong lúc kiểm tra |
| So với `null` | `a.equals(null)` là `false` | Đối tượng hợp lệ và `null` |

Đây là hợp đồng của [Object.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)). Không gọi `null.equals(...)`; đó là dereference một tham chiếu `null`, không phải kiểm tra luật equals.

### 2.1. Không để phép thử bắc cầu trở thành rỗng

Nếu bộ mẫu chỉ có các đối tượng khác nhau hoàn toàn, tiền đề `a.equals(b) && b.equals(c)` hầu như luôn sai. Vòng kiểm tra vẫn chạy và báo PASS nhưng chưa thực sự thử nhóm bằng nhau.

Hãy chủ động tạo:

- Ba instance khác nhau thuộc cùng một nhóm giá trị bằng nhau.
- Instance chỉ khác từng trường có ý nghĩa bằng nhau.
- Instance chỉ khác trường không tham gia bằng nhau, nếu mô hình có trường đó.
- Kiểu khác, đối tượng lớp con hoặc lớp cha nếu thiết kế cho phép và cần hỗ trợ chúng.

Cặp “hai biến cùng trỏ vào một đối tượng” không thay thế được cặp “hai đối tượng độc lập có cùng giá trị”. Nhiều lỗi chỉ xuất hiện khi dữ liệu được đọc lại từ tệp, cơ sở dữ liệu hoặc API thành instance mới.

### 2.2. Kỳ vọng nghiệp vụ phải độc lập với mã đang kiểm thử

Nếu lớp `Key(id, score)` được định nghĩa bằng nhau khi cả `id` và `score` bằng nhau, hãy ghi rõ kỳ vọng:

```text
Key(A, 0) và Key(A, 0): bằng nhau, dù khác instance
Key(A, 0) và Key(B, 0): khác nhau
Key(A, 0) và Key(A, 1): khác nhau
```

Không tạo expected bằng cách gọi lại chính `equals` hoặc dùng một Set làm “chuẩn đúng” duy nhất. Khi đó phép thử có thể chỉ lặp lại lỗi của quan hệ đang cần kiểm tra.

## 3. Kiểm thử hashCode đúng chiều suy luận

Quan hệ bắt buộc là:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

Chiều ngược lại không đúng. Hai đối tượng khác nhau có thể có cùng mã băm; đó là va chạm băm (hash collision), không tự động là lỗi hợp đồng.

Trong cùng một lần thực thi, gọi lại `hashCode` phải cho cùng kết quả khi thông tin dùng cho equals không đổi. Không kiểm thử rằng giá trị hash cụ thể phải giống giữa mọi lần chạy JVM. [Hợp đồng Object.hashCode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#hashCode()).

### Các assertion nên tránh

- `a` khác `b` nên bắt buộc hash khác nhau.
- Hash của đối tượng này luôn phải là một con số đã chụp từ lần chạy trước, khi API không cam kết thuật toán cụ thể.
- Hai đối tượng cùng hash nên phải equals.
- Chỉ cần hash phân bố đẹp là quan hệ equals đã đúng.

Chất lượng phân bố hash là vấn đề hiệu năng riêng. Một hàm luôn trả `0` có thể vẫn đúng hợp đồng nếu equals đúng, nhưng gây nhiều va chạm và thường là lựa chọn hiệu năng kém.

### Kiểm tra qua collection băm

Từ hai instance khác nhau nhưng bằng nhau theo hợp đồng:

1. Thêm instance thứ nhất vào `HashSet`.
2. Thêm instance thứ hai và kiểm tra kích thước không tăng.
3. Dùng instance bằng nhau khác để `contains` và `remove`.
4. Với `HashMap`, đặt giá trị bằng khóa thứ nhất, tra hoặc thay thế bằng khóa bằng nhau, rồi kiểm tra Map vẫn chỉ có một ánh xạ cho khóa đó.

Các phép thử này xác nhận hành vi tích hợp mà ứng dụng thực sự sử dụng. Chúng bổ sung cho kiểm tra luật trực tiếp, không thay thế các fixture nghiệp vụ.

## 4. Comparator: kiểm tra dấu, không học thuộc -1 và 1

`compare(a, b)` trả một số âm, bằng không hoặc dương. Hợp đồng không bắt buộc mọi comparator chỉ trả đúng `-1`, `0`, `1`. Khi kiểm tra quan hệ, dùng dấu của kết quả.

Đặt `s(a,b) = Integer.signum(comparator.compare(a,b))`. Các yêu cầu cốt lõi là:

| Thuộc tính | Phép kiểm tra |
| --- | --- |
| So với chính mình | `compare(a,a) == 0` |
| Đổi thứ tự thì đổi dấu | `s(a,b) == -s(b,a)` |
| Bắc cầu của thứ tự | Nếu `compare(a,b) > 0` và `compare(b,c) > 0` thì `compare(a,c) > 0` |
| Nhóm được coi là hòa phải ứng xử giống nhau | Nếu `compare(a,b) == 0` thì `s(a,c) == s(b,c)` với mọi `c` trong miền |
| Ổn định khi đầu vào và tiêu chí không đổi | Gọi lại không tự đổi quan hệ nhỏ hơn/bằng/lớn hơn |

Nếu phép so sánh với một cặp ném ngoại lệ, đổi thứ tự cặp đó cũng phải ném ngoại lệ theo hợp đồng. Cần kiểm thử riêng miền không hỗ trợ, chẳng hạn `null`, theo chính sách đã công bố. [Hợp đồng Comparator.compare](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html#compare(T,T)).

Không kiểm tra bằng cách viết `compare(a,b) == -compare(b,a)` trên các giá trị nguyên thô. Đó là yêu cầu mạnh hơn hợp đồng, và phép đổi dấu còn có thể tràn ở `Integer.MIN_VALUE`. Chuẩn hóa về dấu rồi đối chiếu tránh lỗi kiểm thử này.

### 4.1. Lỗi phép trừ chỉ hiện rõ ở giá trị biên

Comparator sau không an toàn:

```java
Comparator<Integer> broken = (left, right) -> left - right;
```

Khi phép trừ tràn `int`, dấu có thể sai. Với `left = Integer.MIN_VALUE`, `right = 0`, kết quả âm; đổi chiều tính `0 - Integer.MIN_VALUE` cũng bị tràn và vẫn âm. Hai chiều không còn đổi dấu đúng.

Dùng `Integer.compare(left, right)`, `Comparator.naturalOrder()` hoặc `Comparator.comparingInt(...)` phù hợp với kiểu dữ liệu. Với `long`, dùng cơ chế so sánh cho `long` thay vì ép hiệu xuống `int`.

### 4.2. Kiểm tra ưu tiên và cách xử lý hòa

Comparator `comparingInt(Key::score).thenComparing(Key::id)` nghĩa là so điểm trước; chỉ khi điểm bằng nhau mới so mã. Hãy chuẩn bị các cặp có cùng điểm, khác mã, cùng mã nhưng khác điểm, và các cực trị của điểm.

Thêm `thenComparing` chỉ đúng nếu tiêu chí phụ phù hợp yêu cầu. Không thể khẳng định một chuỗi comparator bất kỳ nhất quán với equals chỉ vì nó có tiêu chí phụ; phải kiểm tra nhóm `compare == 0` có trùng nhóm equals hay không.

## 5. Nhất quán với equals là một yêu cầu cần kiểm tra riêng

Điều kiện nhất quán với equals là:

```text
(compare(a,b) == 0) == a.equals(b)
```

Comparator nói chung có thể không nhất quán với equals và vẫn thỏa các luật thứ tự. Nhưng khi dùng cho `TreeSet` hoặc khóa của `TreeMap`, việc không nhất quán có thể làm collection không tuân thủ hợp đồng chung của Set/Map dựa trên equals. `TreeSet` xác định hai phần tử thuộc cùng vị trí bằng phép so sánh, không bằng một lần gọi equals độc lập. [Tài liệu TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

Ví dụ hai `Key` có cùng điểm `0` nhưng mã `A` và `B`:

- `equals` theo cả hai trường cho `false`.
- Comparator chỉ theo điểm cho `0` và có thể vẫn hợp lệ về các luật comparator.
- `TreeSet` dùng comparator chỉ theo điểm sẽ giữ một phần tử từ hai lần thêm đó.

Nếu mục đích chỉ là sắp xếp List theo điểm, việc hòa giữa các mã có thể là chủ ý. Nếu cần lưu cả hai mã trong Set, cần chọn quan hệ thứ tự phù hợp với danh tính mà Set phải biểu diễn.

### BigDecimal là ví dụ có thật

`new BigDecimal("1.0")` và `new BigDecimal("1.00")` bằng nhau theo giá trị số khi dùng `compareTo`, nhưng `equals` còn phân biệt scale. Vì vậy tập băm và tập cây theo thứ tự tự nhiên có thể có số phần tử khác nhau khi đưa hai giá trị này vào. Đây là hành vi đã được công bố, không phải bằng chứng collection bị hỏng. [Tài liệu BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).

Trong kiểm thử, cần xác định ứng dụng coi scale là thông tin có ý nghĩa hay chỉ quan tâm giá trị số. Không thay quan hệ đó một cách ngầm định khi chuyển loại collection.

## 6. Chương trình Java 17+ kiểm thử bằng các luật

Chương trình sau dùng hàm `check` ném `AssertionError`, vì vậy không cần cờ `-ea`. Nó không cần JUnit hoặc thư viện ngoài. Lưu thành `ContractChecks.java`.

Hợp đồng ví dụ: `Key` có `id` khác `null`; cả `id` và `score` tham gia equals. Comparator đầy đủ so `score` rồi `id`. Các mẫu được giữ nguyên trong suốt quá trình kiểm tra.

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class ContractChecks {
    record Key(String id, int score) {
        Key {
            Objects.requireNonNull(id);
        }
    }

    record CollisionKey(int value) {
        @Override
        public int hashCode() {
            return 0;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static <T> void verifyEquality(List<T> samples) {
        for (T a : samples) {
            check(a != null, "use non-null equality samples");
            check(a.equals(a), "reflexivity: " + a);
            check(!a.equals(null), "null equality: " + a);
            int hash = a.hashCode();
            for (T b : samples) {
                boolean equal = a.equals(b);
                check(equal == b.equals(a), "symmetry: " + a + ", " + b);
                if (equal) {
                    check(a.hashCode() == b.hashCode(), "equal objects need equal hashes");
                }
                for (int repeat = 0; repeat < 3; repeat++) {
                    check(a.equals(b) == equal, "unstable equality");
                    check(a.hashCode() == hash, "unstable hash without mutation");
                }
                for (T c : samples) {
                    if (equal && b.equals(c)) {
                        check(a.equals(c), "transitivity: " + a + ", " + b + ", " + c);
                    }
                }
            }
        }
    }

    static <T> void verifyComparator(
            List<T> samples, Comparator<T> comparator, boolean consistentWithEquals) {
        for (T a : samples) {
            check(comparator.compare(a, a) == 0, "compare self");
            for (T b : samples) {
                int ab = Integer.signum(comparator.compare(a, b));
                int ba = Integer.signum(comparator.compare(b, a));
                check(ab == -ba, "opposite signs: " + a + ", " + b);
                if (consistentWithEquals) {
                    check((ab == 0) == Objects.equals(a, b), "compare zero versus equals");
                }
                for (int repeat = 0; repeat < 3; repeat++) {
                    check(Integer.signum(comparator.compare(a, b)) == ab, "unstable order");
                }
                for (T c : samples) {
                    int bc = Integer.signum(comparator.compare(b, c));
                    int ac = Integer.signum(comparator.compare(a, c));
                    if (ab > 0 && bc > 0) {
                        check(ac > 0, "order transitivity: " + a + ", " + b + ", " + c);
                    }
                    if (ab == 0) {
                        check(ac == bc, "zero group must compare alike against third value");
                    }
                }
            }
        }
    }

    public static void main(String[] args) {
        Key a = new Key("A", 0);
        Key b = new Key("A", 0);
        Key c = new Key("A", 0);
        Key otherId = new Key("B", 0);
        Key otherScore = new Key("A", 1);
        List<Key> samples = List.of(
                a, b, c, otherId, otherScore,
                new Key("MIN", Integer.MIN_VALUE),
                new Key("MAX", Integer.MAX_VALUE));

        check(a != b && a.equals(b), "equal values must include distinct instances");
        check(!a.equals(otherId), "id belongs to equality");
        check(!a.equals(otherScore), "score belongs to equality");
        check(!a.equals("A"), "foreign type");
        verifyEquality(samples);
        System.out.println("equals/hashCode=PASS");

        Set<Key> hashSet = new HashSet<>();
        check(hashSet.add(a), "first insertion");
        check(!hashSet.add(b), "equal insertion must not grow set");
        check(hashSet.contains(c), "lookup through equal distinct object");
        check(hashSet.remove(c) && hashSet.isEmpty(), "remove through equal object");

        Map<Key, String> map = new HashMap<>();
        map.put(a, "first");
        check("first".equals(map.put(b, "found")) && map.size() == 1, "equal key replaces value");
        check("found".equals(map.get(c)), "map lookup through equal object");
        check("found".equals(map.remove(c)) && map.isEmpty(), "map remove through equal object");
        System.out.println("hash collection lookup=PASS");

        Comparator<Key> byScore = Comparator.comparingInt(Key::score);
        Comparator<Key> byScoreThenId = byScore.thenComparing(Key::id);
        verifyComparator(samples, byScore, false);
        verifyComparator(samples, byScoreThenId, true);
        System.out.println("comparator laws=PASS");

        List<Key> sorted = new ArrayList<>(List.of(otherScore, otherId, a));
        sorted.sort(byScoreThenId);
        check(sorted.equals(List.of(a, otherId, otherScore)), "expected business order");
        System.out.println("ordered=" + sorted.stream()
                .map(key -> key.id() + ":" + key.score())
                .toList());

        Set<Key> coarse = new TreeSet<>(byScore);
        coarse.add(a);
        coarse.add(otherId);
        Set<Key> precise = new TreeSet<>(byScoreThenId);
        precise.add(a);
        precise.add(otherId);
        System.out.println("score-only tree size=" + coarse.size());
        System.out.println("score-and-id tree size=" + precise.size());

        List<Key> nullableSamples = new ArrayList<>(samples);
        nullableSamples.add(null);
        verifyComparator(nullableSamples, Comparator.nullsFirst(byScoreThenId), true);
        System.out.println("nullsFirst policy=PASS");

        boolean rejected = false;
        try {
            verifyComparator(
                    List.of(Integer.MIN_VALUE, 0, Integer.MAX_VALUE),
                    (left, right) -> left - right,
                    true);
        } catch (AssertionError ex) {
            rejected = true;
        }
        check(rejected, "subtraction comparator should fail on boundary values");
        System.out.println("subtraction comparator rejected=" + rejected);

        CollisionKey x = new CollisionKey(1);
        CollisionKey y = new CollisionKey(2);
        verifyEquality(List.of(x, new CollisionKey(1), y));
        Set<CollisionKey> collisions = new HashSet<>(List.of(x, y));
        check(collisions.size() == 2, "collision must not merge unequal objects");
        System.out.println("collision set size=" + collisions.size());

        BigDecimal one = new BigDecimal("1.0");
        BigDecimal anotherOne = new BigDecimal("1.00");
        System.out.println("decimal equals=" + one.equals(anotherOne));
        System.out.println("decimal compare zero=" + (one.compareTo(anotherOne) == 0));
        System.out.println("decimal hash set size=" + new HashSet<>(List.of(one, anotherOne)).size());
        System.out.println("decimal tree set size=" + new TreeSet<>(List.of(one, anotherOne)).size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ContractChecks.java
java ContractChecks
```

Stdout chính xác:

```text
equals/hashCode=PASS
hash collection lookup=PASS
comparator laws=PASS
ordered=[A:0, B:0, A:1]
score-only tree size=1
score-and-id tree size=2
nullsFirst policy=PASS
subtraction comparator rejected=true
collision set size=2
decimal equals=false
decimal compare zero=true
decimal hash set size=2
decimal tree set size=1
```

### 6.1. Mỗi nhóm kiểm thử chứng minh điều gì?

- Ba instance `Key("A", 0)` giúp phép thử có nhóm bằng nhau thực sự để kiểm tra bắc cầu, đối xứng và hash.
- Các ca chỉ khác `id` hoặc `score` ghi rõ kỳ vọng nghiệp vụ, thay vì chỉ kiểm tra các luật trừu tượng.
- `HashSet` và `HashMap` được truy cập qua các instance bằng nhau nhưng khác tham chiếu; Map còn kiểm tra thay giá trị và xóa khóa bằng nhau.
- Comparator chỉ theo điểm được kiểm tra các luật với cờ `false`, vì không yêu cầu nó nhất quán với equals trong phép kiểm tra đó.
- Comparator theo điểm rồi mã được kiểm tra với cờ `true`, bổ sung điều kiện `compare == 0` tương đương equals.
- Danh sách đã sắp xếp được đối chiếu với thứ tự kỳ vọng viết độc lập, không tạo expected bằng cách sắp xếp lại bằng cùng comparator.
- `CollisionKey` cố ý trả hash `0` cho mọi giá trị nhưng vẫn phân biệt giá trị trong equals. Set phải giữ cả `1` và `2`.
- Comparator dùng phép trừ bị kiểm tra với cực trị và bị phát hiện vi phạm; chương trình không chờ thuật toán sort tự ném lỗi.

### 6.2. Giới hạn của chương trình

Bộ kiểm tra chỉ xét hữu hạn mẫu. PASS không chứng minh hợp đồng đúng với mọi đối tượng có thể tạo ra. Việc gọi lại ba lần chỉ là kiểm tra thực hành về ổn định trên mẫu, không chứng minh một hàm không phụ thuộc trạng thái ẩn.

Hai hàm có vòng ba tầng, với chi phí O(s³) theo số mẫu `s`. Chúng dành cho tập fixture nhỏ trong kiểm thử, không dành để chạy trên hàng triệu đối tượng ở đường xử lý chính.

`verifyEquality` nhận mẫu khác `null` và kiểm tra `a.equals(null)` bên trong. `verifyComparator` coi các mẫu là miền được phép so; comparator từ chối `null` phải có ca kiểm thử ngoại lệ riêng. Bộ kiểm tra này không tự sinh mọi kiểu ngoại lệ hoặc mọi lớp khác có thể truyền vào equals.

## 7. Chính sách null và tính ổn định của dữ liệu

### 7.1. Comparator cho phép null hay từ chối null?

`Comparator.nullsFirst(base)` và `nullsLast(base)` thêm chính sách cho các tham chiếu phần tử `null`. Trong ví dụ, `nullsFirst` được kiểm tra cả với `null` và các `Key` hợp lệ.

Cần phân biệt phần tử `null` với trường bên trong phần tử là `null`. Bọc comparator bên ngoài bằng `nullsFirst` không tự làm một phép lấy `key.id()` chứa `null` trở nên an toàn với so sánh chuỗi tự nhiên. Nếu trường được phép `null`, cần comparator cho chính trường đó hoặc quy tắc chuẩn hóa rõ ràng.

Nếu chính sách là từ chối `null`, kiểm tra đúng ngoại lệ cho cả `compare(null, a)` và `compare(a, null)` theo hợp đồng. Không biến ca ngoại lệ dự kiến thành “test bị bỏ qua”.

### 7.2. Không dùng kết quả sau khi làm hỏng điều kiện sử dụng collection

Một đối tượng có thể thay đổi các trường được dùng cho equals/hashCode. Nhưng sửa các trường đó khi đối tượng đang là phần tử của Set băm hoặc khóa của Map có thể phá điều kiện mà collection dựa vào. Tài liệu Set cảnh báo hành vi không được xác định nếu thay đổi phần tử làm ảnh hưởng equals khi nó còn ở trong Set. [Tài liệu Set](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html).

Tương tự, thay đổi trường sắp xếp khi phần tử đang nằm trong cấu trúc cây có thể làm thứ tự lưu trữ không còn phản ánh comparator hiện tại. Không viết một phép thử đòi `contains` sau thao tác sử dụng sai đó phải luôn trả đúng một giá trị cụ thể.

Cách kiểm thử thiết kế thường hữu ích hơn:

- Khóa bất biến được tạo đúng và không lộ đối tượng thành phần có thể bị sửa ngoài ý định.
- Nếu cho phép đổi khóa, luồng nghiệp vụ xóa đối tượng khỏi collection trước khi đổi rồi chèn lại đúng cách.
- Các trường chỉ là dữ liệu mô tả có hoặc không tham gia bằng nhau theo hợp đồng đã chọn, và kiểm thử phản ánh điều đó.

## 8. Mở rộng thành kiểm thử dựa trên thuộc tính

Kiểm thử dựa trên thuộc tính (property-based testing) sinh nhiều đầu vào rồi kiểm tra các luật thay vì chỉ vài ví dụ. Để có giá trị, bộ sinh phải chủ động tạo các cấu trúc khó:

1. Sinh một giá trị nền rồi tạo các instance bằng nhau độc lập.
2. Sinh biến thể chỉ khác từng trường có ý nghĩa.
3. Tăng xác suất giá trị biên: `MIN_VALUE`, `MAX_VALUE`, `-1`, `0`, `1`, chuỗi rỗng và độ dài lớn nếu miền cho phép.
4. Sinh cặp hòa theo tiêu chí chính nhưng khác tiêu chí phụ của comparator.
5. Thêm `null` chỉ khi chính sách cho phép; nếu không, kiểm tra miền bị từ chối bằng ca ngoại lệ.
6. Với quan hệ kế thừa được hỗ trợ, sinh cả đối tượng lớp cha/lớp con để kiểm tra đối xứng và bắc cầu giữa chúng.

Ba đối tượng ngẫu nhiên hoàn toàn thường không bằng nhau nên có thể bỏ lỡ nhiều lỗi equals. Cần bộ sinh các nhóm bằng nhau, không chỉ bộ sinh giá trị lẻ.

Lưu seed hoặc tập đầu vào làm lỗi và thu nhỏ về cặp/bộ ba tối thiểu. Thông báo lỗi nên chứa đối tượng, các trường liên quan và dấu kết quả so sánh. Sau khi sửa, giữ ca nhỏ đó như kiểm thử hồi quy ổn định. Không dùng dữ liệu ngẫu nhiên thay đổi khó tái lập làm bằng chứng duy nhất.

Khi đưa vào JUnit, có thể tách từng nhóm luật thành test riêng hoặc test tham số hóa để lỗi cho biết đúng thuộc tính nào thất bại. Các helper cần áp vào lớp và comparator thật của ứng dụng; kiểm thử chỉ một record minh họa không xác nhận các lớp khác trong hệ thống.

## 9. Những phép thử có thể PASS nhưng vẫn bỏ sót lỗi

| Cách kiểm tra thiếu | Vấn đề bị bỏ sót | Cách bổ sung |
| --- | --- | --- |
| Chỉ gọi `a.equals(a)` | Cách so danh tính có thể qua dù sai yêu cầu bằng nhau theo giá trị | Hai instance độc lập cùng giá trị và các biến thể từng trường |
| Chỉ kiểm tra cặp khác nhau | Luật hash khi bằng nhau và bắc cầu có thể không được kích hoạt | Nhóm ba instance bằng nhau |
| Bắt buộc hash của hai giá trị khác nhau phải khác | Đánh trượt va chạm hợp lệ | Chỉ suy từ equals sang hash; thêm ca va chạm qua collection |
| Chỉ sort một danh sách rồi kiểm tra không có lỗi | Nhiều comparator sai không bị phát hiện ở đầu vào đó | Kiểm tra luật theo cặp/bộ ba và thứ tự nghiệp vụ |
| So kết quả compare với đúng `-1` hoặc `1` | Đặt yêu cầu mạnh hơn hợp đồng | So dấu |
| Chỉ dùng các số nhỏ | Lỗi tràn số của phép trừ không lộ | Các cực trị và cặp nằm hai phía miền số |
| Comparator qua luật nên dùng được cho mọi TreeSet | Bỏ qua nhóm `compare == 0` khác nhóm equals | Kiểm tra tính nhất quán với equals và kích thước/tra cứu Set |
| So hai comparator bằng `equals` để suy cách sắp xếp giống nhau | Hai comparator tương đương không bắt buộc phải equals | Đối chiếu quan hệ thứ tự trên mẫu khi đó là mục tiêu test |

Comparator vi phạm hợp đồng có thể bị một thuật toán sắp xếp phát hiện và báo lỗi, nhưng việc không nhận ngoại lệ không phải chứng minh comparator hợp lệ. Hợp đồng API còn coi việc phát hiện vi phạm là tùy chọn ở một số phép sort. [Tài liệu Arrays.sort](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html).

## 10. Bài thực hành

Một lớp `Student` có `studentId`, `displayName` và `score`. Yêu cầu bằng nhau theo `studentId`, còn giao diện cần hiển thị theo điểm giảm dần rồi tên.

1. Viết nhóm fixture để phân biệt luật equals/hashCode với ý nghĩa “cùng sinh viên”. Nếu chỉ đổi tên/điểm mà cùng mã, equals và hash cần quan hệ gì?
2. Kiểm tra comparator hiển thị theo luật và theo thứ tự kỳ vọng, gồm điểm hòa và tên hòa.
3. Hai bản ghi cùng sinh viên nhưng khác điểm có thể được comparator hiển thị phân biệt. Comparator đó có nhất quán với equals không?
4. Nếu cần Set theo danh tính sinh viên, có nên dùng trực tiếp comparator hiển thị cho `TreeSet` không? Xác định cấu trúc hoặc quan hệ phù hợp trước khi viết assertion.
5. Bổ sung các ca biên, chính sách `null` và ca hồi quy cho lỗi đã tìm thấy.

Một bộ kiểm thử tốt nêu rõ vì sao hai đối tượng bằng nhau hoặc vì sao một đối tượng phải đứng trước đối tượng khác. Các luật giúp bắt lỗi cấu trúc; fixture nghiệp vụ giúp giữ đúng ý nghĩa mà ứng dụng cần.
