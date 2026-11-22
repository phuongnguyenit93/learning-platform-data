# Kiểm thử `equals`, `hashCode` và việc dùng record làm khóa trong Java

> **Bối cảnh:** Java 14 → *Thực hành tổng hợp* → **Kiểm thử equals, hashCode và việc dùng record làm khóa**. Record từng được giới thiệu ở **Java 14 dưới dạng preview**, nhưng đã **chính thức từ Java 16 (JEP 395)**. Bài dùng cú pháp **Java 17+ đang được hỗ trợ**, không yêu cầu `--enable-preview` hay API legacy. Trọng tâm là **tự kiểm chứng hợp đồng equality/hashing**, thử `HashMap`/`HashSet` và xử lý những bẫy khi component có trạng thái thay đổi.

## 1. Mục tiêu thực hành và kết quả cần đạt

Sau bài này, bạn cần tự viết và chạy được các phép thử chứng minh:

1. Hai record **cùng record class**, có các component tương đương, thì `equals` trả `true` và `hashCode` trả cùng giá trị.
2. Dùng một record tương đương nhưng **là object khác** làm `HashMap` key vẫn lấy được value; `HashSet` nhận ra trùng lặp.
3. Record **không tự bảo đảm deep immutability**: mảng và collection mutable có thể phá giả định về khóa ổn định.
4. Với array component, `equals` mặc định của record là **so sánh tham chiếu của mảng**, không phải so từng phần tử.
5. Thiết kế khóa đúng bằng **validation/normalization trong canonical constructor**, defensive copying khi cần, và override **`equals` + `hashCode` đồng bộ** nếu semantics khác mặc định.
6. Kiểm thử những góc dễ quên như `null`, double `NaN`, `+0.0`/`-0.0`, cùng những giới hạn của `HashMap` và `TreeMap`.
7. Xác định khi nào một test **chắc chắn đúng** theo hợp đồng Java, và khi nào output chỉ là hành vi tình cờ của một JVM/HashMap instance.

**Bài thực hành chính** là file `RecordKeyChecks.java` chạy được với `javac --release 17`. Bộ kiểm tra dùng `check(...)` chủ động ném `AssertionError` nếu điều kiện sai — **không** phụ thuộc vào việc có thêm JVM flag `-ea`.

## 2. Record thực sự tạo ra những thành viên nào?

Ví dụ ngắn:

~~~java
record UserKey(String tenant, long id) { }
~~~

Theo Java Language Specification (JLS) `8.10, record mang một **danh sách component cố định**. Nếu bạn không tự khai báo thay thế:

- Có các component fields tương ứng, `private final`.
- Có accessors `tenant()` và `id()`.
- Có canonical constructor để khởi tạo components.
- Có `equals(Object)`, `hashCode()` và `toString()` suy ra từ **component values**.
- Record class là `final`, không thể được kế thừa bằng `extends`; vẫn có thể `implements` interfaces.

Các field là `final` giúp **không đổi được tham chiếu hoặc giá trị primitive của component sau khi khởi tạo**, nhưng **không** tự làm object được tham chiếu trở thành bất biến sâu (*deeply immutable*).

### So sánh với lớp thông thường

~~~java
// Đoạn minh họa gần tương đương về API giá trị cơ bản,
// KHÔNG phải bản dịch từng byte của compiler.
final class UserKeyClass {
    private final String tenant;
    private final long id;

    UserKeyClass(String tenant, long id) {
        this.tenant = tenant;
        this.id = id;
    }

    String tenant() { return tenant; }
    long id() { return id; }

    @Override
    public boolean equals(Object other) {
        return other instanceof UserKeyClass k
                && java.util.Objects.equals(tenant, k.tenant)
                && id == k.id;
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(tenant, id);
    }
}
~~~

Đoạn class này nhằm diễn giải **công việc record giúp giảm boilerplate**, không khẳng định compiler record bắt buộc sinh đúng mã đó. JLS không cam kết một thuật toán hash cụ thể hoặc thứ tự so sánh cụ thể trong implementation tự sinh. Nếu bạn cần khóa bền vững, hãy bám **hợp đồng** chứ không sao chép một hash number từ lần chạy JDK trước.

## 3. Hợp đồng `equals` và `hashCode`

### 3.1. `equals`: cùng giá trị không có nghĩa cùng object

~~~java
record Point(int x, int y) { }

// Đặt trong một method:
Point a = new Point(2, 3);
Point b = new Point(2, 3);
Point c = new Point(2, 4);

System.out.println(a == b);      // false: khác object
System.out.println(a.equals(b)); // true: cùng record class và components
System.out.println(a.equals(c)); // false: y khác
~~~

Đây là đoạn minh họa có `record Point` và lệnh trong một method; phần thực hành độc lập đầy đủ ở mục 5.

Các tính chất chuẩn của `Object.equals` cần được tôn trọng:

| Tính chất | Điều cần kiểm tra |
| --- | --- |
| Reflexive | `a.equals(a) == true` |
| Symmetric | `a.equals(b) == b.equals(a)` |
| Transitive | Nếu `a.equals(b)` và `b.equals(c)`, thì `a.equals(c)` |
| Consistent | Khi các giá trị liên quan không thay đổi, kết quả không đổi |
| Non-null | `a.equals(null) == false` |

`equals` do record sinh ra sử dụng **cùng record class** và equality của **tất cả component fields**. Hai record khác class không tự bằng nhau chỉ vì field names và component values trùng.

**Đáng chú ý:** mặc định `equals`/`hashCode` được xác định từ **component fields**, không phải bằng cách gọi accessor có thể được bạn override. Nếu tùy biến accessor trả giá trị khác field, bạn có thể phá invariant tự nhiên: tạo record mới từ các accessor của record cũ nhưng lại không `equals` record cũ. Vì vậy tránh accessors làm “biến dạng” giá trị hiển thị trừ khi có lý do rất rõ.

### 3.2. `hashCode`: bằng nhau thì phải cùng hash, nhưng ngược lại không đúng

Bất biến bắt buộc:

~~~text
a.equals(b) == true
           =>
a.hashCode() == b.hashCode()
~~~

**Không có chiều ngược lại.** Hai object khác nhau vẫn **có thể có cùng `hashCode`** (*hash collision*). Hợp đồng không yêu cầu hash phải duy nhất hoặc định dạng thành chuỗi để làm identifier.

Không kiểm thử bằng cách assert một số hash **cố định** như `key.hashCode() == 123456`, vì cách kết hợp component hashes của record có thể khác giữa implementation/JDK versions. Hãy assert **quan hệ** giữa hash của các object tương đương.

Nếu tự override `equals` mà quên override `hashCode` nhất quán, `HashMap`/`HashSet` có thể hoạt động sai kỳ vọng, dù chương trình vẫn compile.

### 3.3. `HashMap` và `HashSet` dùng cả hai như thế nào?

`HashMap` sử dụng thông tin hash để tổ chức các entries và dùng equality để xác định key tương đương. Một record sinh `equals/hashCode` đúng là lựa chọn **rất thuận tiện** cho khóa có trạng thái ổn định.

~~~java
record OrderKey(String region, long orderId) { }

// Trong method:
java.util.Map<OrderKey, String> cache = new java.util.HashMap<>();
cache.put(new OrderKey("VN", 7), "FOUND");

String result = cache.get(new OrderKey("VN", 7));
// result là "FOUND" vì key mới tương đương key ban đầu.
~~~

Không bắt buộc dùng **chính object key ban đầu** để truy xuất. Tuy nhiên, nếu key chứa state mutable làm equality/hash đổi sau khi thêm vào map, hành vi theo `Map` contract **không còn được bảo đảm**.

`HashSet` tương tự: hai record cùng giá trị được coi là duplicate; số phần tử chỉ tăng khi có một giá trị theo hợp đồng equality chưa tồn tại. `HashMap` không đảm bảo thứ tự duyệt; `HashSet` cũng không dùng thứ tự để đánh giá equality.

## 4. Chi tiết JLS quan trọng khi kiểm thử record

Theo JLS Java 25 `8.10.3:

- Với **reference component**, equality suy từ `equals` của giá trị component (xử lý `null` phù hợp). Ví dụ `String`, `List` dùng equality do class đó định nghĩa.
- Với **primitive component**, equality tương đương kết quả `compare(...) == 0` của wrapper class tương ứng; điều này đặc biệt quan trọng với `float`/`double`.
- `hashCode` từ component hashes: reference component dùng hash của đối tượng được tham chiếu (hoặc zero khi `null`); primitive component dùng hash thích hợp của wrapper.
- Default `equals`/`hashCode` **đọc trực tiếp component fields**, không gọi accessor do lập trình viên tùy biến.
- JLS ràng buộc tính nhất quán của các hàm tự sinh, nhưng **không bắt buộc thuật toán hash kết hợp cụ thể**; không suy đoán hash number theo thứ tự tự đặt.

### 4.1. Mảng: reference equality, không phải deep equality

~~~java
record ArrayKey(int[] values) { }

// Trong method:
ArrayKey first = new ArrayKey(new int[] {1, 2});
ArrayKey second = new ArrayKey(new int[] {1, 2});

System.out.println(first.equals(second)); // false
~~~

Hai mảng có cùng hai số nhưng **khác object**, vì `int[]` không override `Object.equals` theo nội dung. Generated record `equals` vì thế không tự gọi `Arrays.equals`. Hash của mảng cũng là hash theo identity/inherited object behavior, không phải `Arrays.hashCode(int[])`.

**Không cố sửa bằng `Objects.equals(first.values(), second.values())`**: vì với `int[]`, `Objects.equals` vẫn ủy quyền cho equals của array theo tham chiếu. Muốn so nội dung, dùng `Arrays.equals` và hash tương ứng, cùng defensive copies.

### 4.2. `double` và `float`: NaN và signed zero

Với record:

~~~java
record Measurement(double value) { }
~~~

`new Measurement(Double.NaN).equals(new Measurement(Double.NaN))` trả **true**; `new Measurement(+0.0).equals(new Measurement(-0.0))` trả **false**. Đây là ngữ nghĩa record theo wrapper comparison, không phải so sánh `==` trên primitive double (với `==`, `NaN == NaN` là false còn `+0.0 == -0.0` là true).

Đặc biệt khi dùng measurement có double làm key, hãy hiểu rõ cách equality phân biệt **±0** và coi **NaN** tương đương theo quy tắc record. Nếu bài toán nghiệp vụ muốn chuẩn hóa `-0.0` và `+0.0`, hãy quyết định điều đó ở constructor hoặc dùng kiểu giá trị khác cho định danh.

### 4.3. `null` và kiểu component

Một record thông thường **không tự cấm null** với reference components. Nếu bạn muốn khóa không có null, thêm `Objects.requireNonNull(...)` trong canonical constructor. Đừng cho rằng từ khóa `record` tự kiểm tra dữ liệu hợp lệ.

Hai record có cùng giá trị null ở một component có thể bằng nhau nếu các component còn lại tương đương; điều đó không giải quyết việc null có được **nghiệp vụ** chấp nhận hay không.

## 5. Bài thực hành hoàn chỉnh: `RecordKeyChecks.java`

Toàn bộ ví dụ dưới đây có thể biên dịch bằng **`javac --release 17`** trên JDK 17+. Nó kiểm thử cả trường hợp bình thường và những trường hợp dễ làm khóa không ổn định.

**File: `RecordKeyChecks.java`**

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class RecordKeyChecks {
    record UserKey(String tenant, long id) {
        UserKey {
            tenant = Objects.requireNonNull(tenant, "tenant")
                    .strip().toLowerCase(Locale.ROOT);
            if (id <= 0) {
                throw new IllegalArgumentException("id must be positive");
            }
        }
    }

    record ScoresKey(int[] scores) { }

    record SafeScoresKey(int[] scores) {
        SafeScoresKey {
            scores = Objects.requireNonNull(scores, "scores").clone();
        }

        @Override
        public int[] scores() {
            return scores.clone();
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof SafeScoresKey other
                    && Arrays.equals(scores, other.scores);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(scores);
        }
    }

    record MutableTagsKey(List<String> tags) { }

    record FrozenTagsKey(List<String> tags) {
        FrozenTagsKey {
            tags = List.copyOf(tags);
        }
    }

    record Measurement(double value) { }

    static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        UserKey a = new UserKey(" Tenant-A ", 7);
        UserKey b = new UserKey("tenant-a", 7);
        UserKey c = new UserKey("TENANT-A", 7);
        UserKey different = new UserKey("tenant-a", 8);

        check(a != b, "different object references");
        check(a.equals(a), "reflexivity");
        check(a.equals(b) && b.equals(a), "symmetry");
        check(a.equals(b) && b.equals(c) && a.equals(c),
                "transitivity");
        check(!a.equals(different), "different id");
        check(a.hashCode() == b.hashCode(), "equal hashes");

        Map<UserKey, String> users = new HashMap<>();
        users.put(a, "ACTIVE");
        check("ACTIVE".equals(users.get(b)), "HashMap lookup");

        Set<UserKey> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        unique.add(c);
        check(unique.size() == 1, "HashSet dedup");
        System.out.println("recordEquals=" + a.equals(b));
        System.out.println("equalHash=" + (a.hashCode() == b.hashCode()));
        System.out.println("mapLookup=" + users.get(b));
        System.out.println("setSize=" + unique.size());

        ScoresKey rawA = new ScoresKey(new int[]{4, 5});
        ScoresKey rawB = new ScoresKey(new int[]{4, 5});
        check(!rawA.equals(rawB), "array uses reference equality");
        System.out.println("arrayRecordEquals=" + rawA.equals(rawB));

        int[] input = {4, 5};
        SafeScoresKey safeA = new SafeScoresKey(input);
        SafeScoresKey safeB = new SafeScoresKey(new int[]{4, 5});
        Map<SafeScoresKey, String> scores = new HashMap<>();
        scores.put(safeA, "SAVED");
        check(safeA.equals(safeB), "content equality");
        check(safeA.hashCode() == safeB.hashCode(), "content hash");
        input[0] = 99;
        safeA.scores()[0] = 77;
        check(safeA.scores()[0] == 4, "defensive copying");
        check("SAVED".equals(scores.get(safeB)), "stable array key");
        System.out.println("safeArrayEquals=" + safeA.equals(safeB));
        System.out.println("safeArrayLookup=" + scores.get(safeB));

        List<String> inputTags = new ArrayList<>(List.of("x"));
        MutableTagsKey mutable = new MutableTagsKey(inputTags);
        int hashBefore = mutable.hashCode();
        Map<MutableTagsKey, String> risky = new HashMap<>();
        risky.put(mutable, "RISK");
        inputTags.add("y");
        check(hashBefore != mutable.hashCode(), "hash changed");
        System.out.println("mutableHashChanged=" +
                (hashBefore != mutable.hashCode()));

        FrozenTagsKey frozen = new FrozenTagsKey(inputTags);
        Map<FrozenTagsKey, String> stable = new HashMap<>();
        stable.put(frozen, "STABLE");
        inputTags.add("z");
        check(frozen.tags().equals(List.of("x", "y")),
                "snapshot not altered");
        check("STABLE".equals(
                stable.get(new FrozenTagsKey(List.of("x", "y")))),
                "frozen lookup");
        System.out.println("frozenTags=" + frozen.tags());
        System.out.println("frozenLookup=" +
                stable.get(new FrozenTagsKey(List.of("x", "y"))));

        check(new Measurement(Double.NaN).equals(
                new Measurement(Double.NaN)), "NaN equality");
        check(!new Measurement(+0.0).equals(
                new Measurement(-0.0)), "signed zeros differ");
        System.out.println("nanEquals=" +
                new Measurement(Double.NaN).equals(
                        new Measurement(Double.NaN)));
        System.out.println("signedZerosEqual=" +
                new Measurement(+0.0).equals(new Measurement(-0.0)));
        System.out.println("allChecksPassed");
    }
}
~~~

### 5.1. Biên dịch và chạy

Đặt file ở một thư mục thực hành riêng rồi chạy:

~~~bash
javac --release 17 -encoding UTF-8 RecordKeyChecks.java
java RecordKeyChecks
~~~

**Stdout chính xác đã kiểm chứng trên JDK 24 với target Java 17:**

~~~text
recordEquals=true
equalHash=true
mapLookup=ACTIVE
setSize=1
arrayRecordEquals=false
safeArrayEquals=true
safeArrayLookup=SAVED
mutableHashChanged=true
frozenTags=[x, y]
frozenLookup=STABLE
nanEquals=true
signedZerosEqual=false
allChecksPassed
~~~

Cả bước biên dịch và chạy đều có **exit code 0** trên môi trường kiểm thử. Không cần `--enable-preview` cho Java 17+ vì record đã là tính năng chính thức.

Nếu thay đổi một bất biến trong code và điều kiện `check(...)` sai, chương trình ném **`AssertionError`** với nhãn kiểm thử; đây là một phép thử chủ động, không phải chỉ in kết quả để con người tự đoán.

### 5.2. Các nhóm test đang chứng minh gì?

| Nhóm | Assert | Ý nghĩa |
| --- | --- | --- |
| Equality cơ bản | `a.equals(a)`, đối xứng/bắc cầu, khác id | Hợp đồng equality |
| Hash tương ứng | `a.hashCode() == b.hashCode()` | Hai record bằng nhau phải cùng hash |
| HashMap | `users.get(b) == "ACTIVE"` theo content check | Key tương đương truy được mapping |
| HashSet | `unique.size() == 1` | a, b, c sau chuẩn hóa trùng cùng một key |
| Array default | `!rawA.equals(rawB)` | Array component không so nội dung mặc định |
| Safe array | `safeA.equals(safeB)`, hash tương ứng, lookup | Override `equals/hashCode` và clone đúng |
| Mutable list | `hashBefore != mutable.hashCode()` | Mutable component có thể làm hash thay đổi |
| Immutable snapshot | `frozen.tags()` và lookup sau sửa list gốc | `List.copyOf` giữ snapshot và hash ổn định trong ví dụ |
| Floating-point | NaN bằng NaN, +0 khác -0 | Ngữ nghĩa `compare` wrapper của record |

**Một điều quan trọng:** chương trình **không** assert `risky.get(mutable) == null` sau mutation. Khi key thay đổi hash, Map contract không còn đảm bảo kết quả; với một số hash bucket/collisions kết quả có thể tình cờ vẫn tìm thấy. Test có tính tổng quát nên chỉ khẳng định **hash đã thay đổi** và **việc dùng key mutable là sai hợp đồng**.

## 6. Chuẩn hóa khóa ngay trong canonical constructor

Trong code, `UserKey` có compact canonical constructor:

~~~java
record UserKey(String tenant, long id) {
    UserKey {
        tenant = java.util.Objects.requireNonNull(tenant, "tenant")
                .strip().toLowerCase(java.util.Locale.ROOT);
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
    }
}
~~~

Điều này là **Java 17+ hợp lệ**, không cần trực tiếp gán `this.tenant`/`this.id` trong compact constructor. Sau khi thân compact constructor chạy, các giá trị tham số đã chuẩn hóa được dùng để khởi tạo component fields theo quy tắc của record.

**Vì sao có ích khi làm Map key?**

- `new UserKey(" Tenant-A ", 7)` và `new UserKey("tenant-a", 7)` có cùng representation nội bộ.
- `new UserKey("TENANT-A", 7)` cũng cùng representation nhờ `Locale.ROOT`.
- `tenant` không thể null; `id` buộc dương theo yêu cầu ví dụ.
- Generated `equals/hashCode` đủ dùng, không cần viết logic equality thủ công.

**Cảnh báo về nghiệp vụ:** normalization chỉ nên áp dụng khi **định nghĩa định danh** của dự án thật cho phép. Một mã tài khoản phân biệt chữ hoa/thường không được tự chuyển lowercase, vì có thể hợp nhất nhầm các thực thể khác nhau. `strip()` chỉ loại bỏ whitespace Unicode theo quy tắc Java, không phải mọi ký tự vô hình; cần policy rõ ràng.

### 6.1. Vì sao không normalize trong accessor?

Ví dụ style không nên dùng cho key:

~~~java
// MINH HỌA STYLE SAI: không dùng làm thiết kế key.
record BadView(String code) {
    @Override
    public String code() {
        return code.toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

Generated `equals/hashCode` vẫn dùng **field `code` gốc**, không dùng `code()` đã lowercase. Nếu code nội bộ lưu `"ABC"`, một bản copy được tạo từ `new BadView(original.code())` có thể lưu `"abc"`; hai record bấy giờ không equal theo field mặc dù accessor hiển thị cùng giá trị.

**Giải pháp:** normalize ở canonical constructor trước khi lưu field, để accessor trả đúng state được dùng cho equality. Trong một value object, hành vi getter và equality nên phù hợp với bất biến sao chép nêu tại JLS.

## 7. Hai bẫy nguy hiểm nhất với Map key: mảng và collection mutable

### 7.1. Record giữ reference tới mảng mutable

~~~java
record ScoresKey(int[] scores) { }
~~~

Record có component field `final` nhưng **nội dung mảng vẫn có thể đổi**:

~~~java
int[] raw = {10, 20};
ScoresKey key = new ScoresKey(raw);
raw[0] = 99;           // Sửa mảng bên trong record!
key.scores()[1] = 88; // Accessor mặc định trả reference gốc.
~~~

Mã minh họa trên phải đặt bên trong method có `ScoresKey`. `final` chỉ giữ không đổi **tham chiếu `scores`**, không khóa nội dung array. Với default equals/hash theo identity, **mutation phần tử array không nhất thiết làm hash key đổi**, nhưng nó cho phép trạng thái nội bộ thay đổi và làm định nghĩa khóa theo **nội dung** không thể đạt được. Không được nói rằng **mọi** array mutation làm record default hash đổi: với array, hash mặc định gắn identity.

**Nếu nhu cầu là equality theo nội dung array**, phải chủ động thay cả `equals` và `hashCode` thành `Arrays.equals`/`Arrays.hashCode` đồng bộ.

### 7.2. Defensive copy ở **đầu vào và đầu ra**

Code `SafeScoresKey` trong ví dụ làm ba việc:

1. **Constructor clone:** `scores = scores.clone();` giúp người gọi không sửa array lưu bên trong bằng reference cũ.
2. **Accessor clone:** `public int[] scores() { return scores.clone(); }` giúp người gọi không dùng getter sửa array nội bộ.
3. **Override cả hai methods:** `Arrays.equals(scores, other.scores)` và `Arrays.hashCode(scores)` giúp equality/hashing dựa trên **nội dung** array.

**Không đủ nếu chỉ clone constructor mà accessor trả thẳng mảng**, vì client vẫn có thể sửa qua `key.scores()[i]`. **Không đủ nếu chỉ override equals** mà giữ hash mặc định, vì hai record có arrays khác identity nhưng cùng nội dung có thể equal trong custom equals song hash mặc định vẫn khác.

**Giới hạn:** clone một array một chiều của primitive cho snapshot nội dung đúng. Với mảng nhiều chiều hoặc array chứa objects mutable, `clone()` chỉ là **shallow copy**; cần thiết kế deep copy/immutable element phù hợp.

### 7.3. Collection: record field final nhưng `List` có thể thay đổi

~~~java
record MutableTagsKey(java.util.List<String> tags) { }
~~~

Một `ArrayList` có `equals` và `hashCode` theo **nội dung phần tử**. Do đó nếu người gọi thêm phần tử sau khi record đã làm `HashMap` key, **hash code của record có thể đổi**.

Ví dụ ở mục 5:

~~~java
List<String> inputTags = new ArrayList<>(List.of("x"));
MutableTagsKey key = new MutableTagsKey(inputTags);
int before = key.hashCode();

inputTags.add("y");
boolean changed = before != key.hashCode(); // true ở demo
~~~

**Lưu ý:** các dòng là minh họa trong method với imports phù hợp; trong chương trình chính, `changed` được kiểm thử bằng `check`. Không dựa vào việc `HashMap.get` có trả `null` cụ thể hay không sau mutation: theo `Map` specification, hành vi không được xác định khi key thay đổi theo cách ảnh hưởng equality trong lúc key vẫn nằm trong Map.

### 7.4. Snapshot bất biến bằng `List.copyOf`

~~~java
record FrozenTagsKey(java.util.List<String> tags) {
    FrozenTagsKey {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

`List.copyOf` tạo (hoặc tái sử dụng) danh sách **unmodifiable** biểu diễn snapshot nội dung hiện tại. Nếu input là một `ArrayList<String>` rồi bạn thay đổi input, record giữ danh sách ban đầu. Vì `String` cũng immutable, cấu trúc của khóa ví dụ ổn định và `HashMap` lookup bằng một `FrozenTagsKey` tương đương vẫn hoạt động.

**Không khẳng định `List.copyOf` deep copy mọi thứ.** Nó không nhân bản sâu từng phần tử; một `List<MutablePerson>` vẫn có thể chứa object có `equals/hashCode` thay đổi theo thời gian. Nó cũng **không cho phép null elements**, nên dữ liệu có null cần được validate hoặc chọn representation phù hợp.

### 7.5. Nguyên tắc thiết kế khóa an toàn

- Ưu tiên component `String`, `long`, `UUID`, `enum` và các immutable value objects có equality/hashing nhất quán.
- Với collections, tạo immutable snapshot của cả cấu trúc và **bảo đảm elements cũng ổn định**.
- Với arrays, cân nhắc chuyển thành immutable list khi đúng semantics hoặc tự viết equals/hash cùng defensive copying.
- Không đặt vào key những component phụ thuộc thời gian, counter mutable, cache không ổn định, nội dung data structures được chia sẻ và thay đổi.
- Nếu object thay đổi về mặt nghiệp vụ, hãy **tạo key mới** rồi cập nhật Map bằng thao tác có kiểm soát thay vì sửa state của key đang tồn tại.

## 8. Khi override `equals`, cần nghĩ đến `hashCode` cùng lúc

Record cho phép explicit implementations `equals`, `hashCode`, `toString`, nhưng bạn phải giữ hợp đồng. Lỗi rất dễ gặp:

~~~java
// MINH HỌA THIẾT KẾ SAI: chỉ override equals.
record BrokenCodeKey(String code) {
    @Override
    public boolean equals(Object obj) {
        return obj instanceof BrokenCodeKey other
                && code.equalsIgnoreCase(other.code);
    }
}
~~~

Đoạn này có thể compile; tuy nhiên generated `hashCode` vẫn dựa trên giá trị `code` gốc và không tự biết rằng bạn muốn so sánh không phân biệt hoa/thường. Hai object với `code` là `"A"` và `"a"` có thể được custom equals xem là equal nhưng hash khác, **vi phạm hợp đồng**.

**Cách sửa khuyến nghị**: normalize ở compact canonical constructor và **không override** `equals/hashCode` nếu definition nghiệp vụ phù hợp. Nếu thật sự muốn custom equality, hãy định nghĩa **cả hai**:

~~~java
record CaseInsensitiveCodeKey(String code) {
    CaseInsensitiveCodeKey {
        java.util.Objects.requireNonNull(code, "code");
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof CaseInsensitiveCodeKey other
                && code.equalsIgnoreCase(other.code);
    }

    @Override
    public int hashCode() {
        return code.toLowerCase(java.util.Locale.ROOT).hashCode();
    }
}
~~~

**Đây là minh họa chính sách chỉ với code strings**; `String.equalsIgnoreCase` và `toLowerCase(Locale.ROOT)` có những khác biệt Unicode edge cases. Không lấy công thức này làm **bằng chứng phổ quát** rằng mọi cặp mà `equalsIgnoreCase` coi bằng nhau sẽ có cùng lowercase representation theo mọi ký tự Unicode. Để có hợp đồng thật sự chặt, hãy **chọn một canonical normalization policy nhất quán**, dùng cùng canonical form trong `equals` và `hashCode`, hoặc giới hạn bộ ký tự đầu vào theo nghiệp vụ (chẳng hạn mã ASCII).

Vì vậy **đối với khóa quan trọng** hãy ưu tiên `UserKey` đã normalize **một lần ở constructor**. Đây là phương án đơn giản nhất để đảm bảo equals/hash cùng nhìn một state ổn định.

**Quy tắc reviewer:** không phê duyệt override `equals` nếu chưa xem kỹ `hashCode`; không dùng một hash function không nhất quán với equality semantics.

## 9. Kiểm thử có cấu trúc: nên assert gì, không nên assert gì?

### 9.1. Test đúng

| Tình huống | Assert nên dùng |
| --- | --- |
| Reflexivity | `a.equals(a)` |
| Symmetry | `a.equals(b) == b.equals(a)` |
| Transitivity | `a≈b` và `b≈c` thì `a≈c` |
| Different component | `!a.equals(different)` |
| Equal hash | `a.equals(b)` và `a.hashCode()==b.hashCode()` |
| Equivalent lookup | `map.put(a,"v"); map.get(b).equals("v")` |
| Dedup | `HashSet.add(a)` rồi `HashSet.add(b)` làm size không đổi |
| Array content | Với custom equality: `Arrays.equals(...)` và hash cùng |
| Mutable component | Chứng minh hash thay đổi hoặc equality thay đổi khi input bị sửa |
| Defensive copy | Sửa input/getter output không đổi nội dung key đã lưu |
| Floating-point | NaN==NaN theo record; +0 khác -0 |
| Validation | Constructor từ chối null/sai id theo contract |
| Data-based copy | `r.equals(new R(r.c1(), ..., r.cn()))` nếu accessors phù hợp |

### 9.2. Test không đáng tin

- Assert **một con số hashCode** cố định giữa các JDK hoặc các JVM executions.
- Assert **hai key khác nhau bắt buộc có hashCode khác nhau**: hash collisions hợp lệ.
- Assert **HashMap duyệt theo thứ tự insert**: không có hợp đồng giữ thứ tự.
- Assert **HashMap.get phải trả null** sau khi một key bị sửa: behavior đã ngoài hợp đồng, có thể tình cờ khác theo bucket.
- Assert record luôn **deep immutable** chỉ vì có fields `final`.
- Assert các keys có cùng `toString()` nhất thiết equal; `toString` phục vụ mô tả, không quyết định equality.
- Assert mọi `TreeMap<Record,...>` dùng được mặc định: record **không tự implements Comparable**.
- Dùng `assert` trong Java mà quên `-ea`, khiến test có thể bị bỏ qua khi chạy; `check`/JUnit assertions là lựa chọn rõ ràng.

### 9.3. Nếu dùng JUnit thì tổ chức test thế nào?

Bộ test thường nên chia các test methods tách biệt:

1. `equalRecordsHaveEqualHashes`: a,b,c với cùng canonical values.
2. `equalKeyRetrievesHashMapValue`: put và get bằng object khác.
3. `duplicateValueIsOneHashSetEntry`: insert nhiều equal values.
4. `defaultArrayRecordIsReferenceBased`: array distinct references không equal.
5. `safeArrayDefensiveCopy`: đổi input và accessor clone không ảnh hưởng key.
6. `mutableListIsUnsuitableAsKey`: thay đổi làm hash/equality thay đổi.
7. `canonicalConstructorRejectsInvalidKey`: null, non-positive id.
8. `floatingPointEdgeCases`: NaN, signed zeros.
9. `caseInsensitivePolicyConsistent`: canonicalization xác định duy nhất nghĩa của key.
10. `mutationOfExternalSourceDoesNotChangeFrozenKey`: snapshot giữ nguyên.

Ở đây chương trình dùng `check(...)` để có **bộ test chạy trực tiếp không cần dependency**. Với dự án JUnit, chuyển các trường hợp thành `@Test` và assertions của **JUnit Jupiter** theo version dependency của build, nhưng **không** copy các lệnh compile độc lập trên sang một file chứa JUnit khi chưa thêm JUnit dependencies.

### 9.4. Test property-based và nhiều giá trị

Một số lỗi equality chỉ xuất hiện với dữ liệu Unicode, null, số biên hoặc dữ liệu đã chuẩn hóa. Các phép thử mở rộng đáng cân nhắc:

- Generate nhiều chuỗi khác hoa/thường/whitespace theo phạm vi ký tự ứng dụng cho phép.
- Generate positive ids và một số ids không hợp lệ để thử constructor.
- Với một bộ records, nếu `a.equals(b)` thì assert hashes bằng nhau.
- Thử rất nhiều record keys trong `HashMap` để nhận diện định nghĩa key có tạo trùng bất thường không; đừng dựa vào thứ tự duyệt.
- Thử snapshot collection sau khi sửa dữ liệu nguồn.
- Thử null constraints và những giá trị đặc biệt của `double`.
- Thử concurrency theo công cụ phù hợp nếu map được chia sẻ đa luồng.

## 10. Những giới hạn khác khi dùng record làm khóa

### 10.1. `HashMap` khác `TreeMap`

`HashMap` dùng `hashCode` và `equals`. `TreeMap` dùng **thứ tự so sánh** theo `Comparator` hoặc `Comparable`; record **không tự implements Comparable`.

Ví dụ:

~~~java
record CustomerKey(long id, String region) { }

// Trong method:
java.util.Map<CustomerKey, String> map = new java.util.TreeMap<>(
        java.util.Comparator.comparingLong(CustomerKey::id)
                .thenComparing(CustomerKey::region));

map.put(new CustomerKey(3, "VN"), "ok");
~~~

**Quan trọng:** với `TreeMap`, comparator phải nhất quán với equality nếu muốn `Map` semantics tương thích với `equals` của key. Nếu comparator chỉ so `id` mà bỏ `region`, `new CustomerKey(3,"VN")` và `new CustomerKey(3,"US")` có thể bị xem là cùng vị trí key dù generated `equals` nói khác nhau.

### 10.2. ConcurrentHashMap không sửa được key mutable

`ConcurrentHashMap` phù hợp khi có nhiều threads truy cập chung map theo hợp đồng concurrent collection; nó **không** làm một key chứa mutable list tự ổn định. Hash/equality của key vẫn phải nhất quán.

Lưu ý `HashMap` không được đồng bộ hóa mặc định; nếu nhiều threads cập nhật structural entries cần synchronization hoặc concurrent map thích hợp. Việc sử dụng record làm khóa **không tự biến `HashMap` thành thread-safe**.

### 10.3. Không dùng hash code làm định danh bền vững

`hashCode()` không phải ID unique, không có hợp đồng bất biến giá trị numeric qua các bản JDK hoặc giữa các process khác nhau. Không dùng nó như khóa chính database, checksum, content hash bảo mật hoặc dữ liệu cần trao đổi giữa services.

Nếu cần stable external ID, dùng **các components chuẩn hóa** hoặc một identifier/schema riêng. Ví dụ `UserKey(tenant,id)` có thể được biểu diễn thành hai field với format đã version hóa, thay vì lưu `UserKey.hashCode()` như mã khách hàng.

### 10.4. `toString` và bảo mật

Generated `toString` chứa biểu diễn **tất cả components**. Dùng record với secrets, access tokens hoặc dữ liệu nhạy cảm rồi log key có thể vô tình lộ thông tin. Đừng thiết kế key chứa secrets chỉ vì tiện và cũng đừng log `key.toString()` trong môi trường production thiếu kiểm soát.

### 10.5. Records không bắt buộc là DTO toàn năng

Record là **value carrier** rất tốt khi state thực sự được mô tả bằng components. Nếu một thực thể nghiệp vụ có identity độc lập với một số fields thường xuyên thay đổi, có lifecycle/phân quyền phức tạp hoặc cần kế thừa class, không nên ép tất cả thành record key có đầy đủ mutable fields. Hãy phân biệt **entity identity** với snapshot dữ liệu hiện tại.

## 11. Tình huống review: sai ở đâu, sửa thế nào?

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Hai record cùng text nhưng `equals=false` | Khác record class, chưa normalize, null/whitespace khác | Xác định danh tính và chính sách canonicalization |
| `map.get(new Key(...))` trả `null` | Sai components, key mutable, semantics equals/hash không khớp | Test bằng key equal theo contract, kiểm tra state và hash stability |
| Hai arrays cùng nội dung nhưng record key không equal | Mảng dùng identity equality | `Arrays.equals/hashCode` + defensive copies, hoặc immutable representation |
| Thay phần tử array từ accessor không đổi default hash | Hash mặc định của array theo identity; nhưng state vẫn mutable | Không lầm đây là key theo nội dung; clone input/output |
| Thay phần tử List làm hash thay đổi | List mutable và hash dựa nội dung | `List.copyOf`/immutable snapshot, kiểm soát elements |
| Override `equals` nhưng Map lookup thất bại | `hashCode` không đồng bộ với equality | Đồng bộ hai methods hoặc canonicalize một lần |
| So sánh NaN/signed zero bất ngờ | Record primitive uses wrapper comparison semantics | Test NaN và ±0.0, chọn normalization |
| `TreeMap` lỗi class cast | Record không comparable | Cung cấp Comparator nhất quán hoặc implement Comparable |
| Test pass khi chạy mà không bật assertions | `assert` bị tắt theo mặc định | Dùng check/JUnit hoặc bật `java -ea` có chủ đích |
| Phụ thuộc fixed hash value | JLS không bảo đảm thuật toán hash cụ thể | Assert equal=>same hash, không assert literal number |
| Record chứa List unmodifiable nhưng nested object mutable | `List.copyOf` shallow | Snapshot elements hoặc chọn immutable element types |
| Logging key lộ thông tin | `toString` sinh từ components | Tránh secrets trong key, hạn chế log, cân nhắc manual safe representation |

**Cách debug ưu tiên:** in (trong môi trường an toàn) tên record class và **component values**, so sánh `equals`, hash quan hệ, kiểm tra mutation và bản thân container map. Không dựa vào một số hash duy nhất để suy ra nguyên nhân.

## 12. Checklist trước khi phát hành một record key

- [ ] Đã định nghĩa rõ **identity của khóa** và các components tham gia equality.
- [ ] Record dùng cú pháp Java 17+ ổn định, không yêu cầu preview của Java 14.
- [ ] Generated `equals/hashCode` phù hợp semantics của từng component.
- [ ] Có test **reflexive, symmetric, transitive, null, equal hashes**.
- [ ] Có test `HashMap.put/get` bằng **hai object khác instance nhưng equal**.
- [ ] Có test `HashSet` duplicate behavior.
- [ ] Components có giá trị và hash **ổn định** trong suốt thời gian làm key.
- [ ] Nếu cần normalize, đã làm trong canonical constructor và xác định policy rõ.
- [ ] Nếu dùng array, đã quyết định **identity hay content equality** và xử lý defensive copies.
- [ ] Nếu dùng collection, dữ liệu là immutable snapshot và elements ổn định.
- [ ] Nếu override `equals`, `hashCode` được override tương ứng theo đúng semantics.
- [ ] Đã test floating-point NaN, signed zeros nếu có float/double components.
- [ ] Không assert exact hash numbers, HashMap iteration order hoặc Map behavior sau mutation.
- [ ] Nếu dùng `TreeMap`, có Comparator/Comparable nhất quán với equality.
- [ ] Nếu dùng map đa luồng, đã chọn cấu trúc/synchronization phù hợp.
- [ ] Không lưu hashCode làm ID lâu dài hay log record key có secrets.

## 13. Bài tập tự luyện

1. Tạo `record Point(int x,int y)` rồi kiểm tra `==` khác `equals`; viết test reflexive/symmetric/transitive.
2. Tạo `Map<UserKey,String>`, put với `new UserKey(" Vn ", 1)`, get bằng `new UserKey("vn",1)`. Vì sao lookup thành công trong thiết kế constructor ở mục 5?
3. Thêm ba `UserKey` cùng canonical values vào `HashSet`. Dự đoán `size` và kiểm tra.
4. Với `record BytesKey(byte[] data)`, hai keys chứa hai mảng mới nhưng cùng bytes có equal không? Tại sao?
5. Viết defensive-copy constructor và accessor cho `byte[]`, override `equals/hashCode` bằng `Arrays.equals/hashCode`; kiểm thử sửa mảng gốc không tác động key.
6. Dùng `record TagsKey(List<String> tags)` chứa `ArrayList`, put vào `HashMap` rồi sửa list. Vì sao không nên assert cứng `get(key) == null`?
7. Dùng `List.copyOf` để giữ snapshot list đầu vào. Nếu elements trong list là mutable objects, còn rủi ro nào?
8. Đổi `UserKey` thành không normalize, quan sát equality giữa `"Tenant-A"` và `"tenant-a"`. Chính sách nào đúng theo nghiệp vụ?
9. Với `record Measurement(double value)`, dự đoán kết quả so hai NaN và so `+0.0` với `-0.0`.
10. Tạo một record override `equals` không phân biệt chữ hoa/thường nhưng giữ `hashCode` mặc định; kiểm tra vì sao vi phạm hợp đồng và cách sửa bằng normalization.
11. Dùng `TreeMap` với Comparator chỉ so id và một record `CustomerKey(id,region)`. Hai keys có cùng id nhưng region khác sẽ bị coi thế nào?
12. Chạy toàn bộ `RecordKeyChecks.java` rồi thay đổi một kỳ vọng trong `check(...)` để thấy phép thử tự fail không cần `-ea`.
13. Nếu record key được log và có component `secretToken`, những nguy cơ từ `toString` tự sinh là gì?
14. Viết các property tests: với mọi cặp keys mà `equals=true` thì hash bằng nhau; với tập có ba keys a,b,c equal, `HashSet` size bằng 1.

## 14. Tài liệu chính thống và vẫn áp dụng

- [Oracle Java SE 25 – Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): canonical constructor, accessors, equality/hashCode và các giới hạn của record.
- [JLS Java SE 25 – `8.10.3 Record Members`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.3): quy tắc generated equals/hash, reference/primitive comparisons, nội dung fields trực tiếp, invariant sao chép.
- [Oracle Java SE 25 – `java.lang.Record`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html): shallowly immutable value carrier, hợp đồng equality/hash.
- [Oracle Java SE 25 – `java.util.Map`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): cảnh báo khi mutable key thay đổi theo cách ảnh hưởng equals.
- [Oracle Java SE 25 – `java.util.HashMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashMap.html): hash lookup, thứ tự không đảm bảo và concurrency constraints.
- [Oracle Java SE 25 – `java.util.Arrays`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html): `Arrays.equals`/`Arrays.hashCode` cho arrays.
- [Oracle Java SE 25 – `java.util.List`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): `List.copyOf`, shallow unmodifiable snapshots và điều kiện null.
- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395): record chính thức từ Java 16, sau preview Java 14–15.

**Ghi nhớ:** record là cách ngắn gọn để mô tả **value-based key**, không phải chiếc hộp làm mọi component bất biến. Kiểm thử phải chứng minh **cùng giá trị ⇒ `equals=true` và cùng `hashCode`**, `HashMap`/`HashSet` nhận khóa tương đương, và không có mutable state âm thầm làm đổi hash. Với arrays, phải chọn content equality và defensive copying; với collections, cần snapshot bất biến. **Giữ đúng hợp đồng equality/hashing và thiết kế key ổn định** quan trọng hơn việc record giúp viết ít dòng code.