# Kiểm thử số ngẫu nhiên bằng seed hoặc nguồn được truyền vào trong Java

## 1. Vì sao code có yếu tố ngẫu nhiên khó kiểm thử?

Một chức năng dùng số ngẫu nhiên có thể chọn phần tử, mô phỏng xúc xắc, lấy mẫu telemetry, quyết định nhánh A/B, sinh dữ liệu thử nghiệm hoặc thêm độ trễ *jitter*. Nếu mỗi lần chạy test đều lấy nguồn ngẫu nhiên mới, một test có thể thành công nhiều lần rồi thất bại trong CI dù code không đổi. Tình trạng này gọi là **flaky test**: kết quả không ổn định do test phụ thuộc dữ liệu không kiểm soát.

Ví dụ khó kiểm thử:

~~~java
public static int rollDie() {
    return new java.util.Random().nextInt(6) + 1;
}
~~~

Mỗi lần gọi tạo một đối tượng `Random` mới rồi sinh giá trị bất kỳ từ 1 đến 6. Một test viết `assertEquals(4, rollDie())` không có cơ sở: 4 chỉ là một kết quả khả dĩ.

Hai kỹ thuật quan trọng:

1. **Cố định seed** cho một bộ sinh số giả ngẫu nhiên (PRNG) để lặp lại chuỗi khi cùng thuật toán, seed và thứ tự gọi.
2. **Truyền nguồn sinh số ngẫu nhiên từ ngoài vào** (*dependency injection*) để code nghiệp vụ không tự tạo nguồn; test có thể cung cấp PRNG cố định seed hoặc nguồn giả lập có kết quả định trước.

Đây là bài về **thiết kế kiểm thử và chẩn đoán**, không phải hướng dẫn tạo số ngẫu nhiên dùng cho bảo mật. Với token, mật khẩu, khóa mật mã hoặc nonce bảo mật, phải dùng `SecureRandom` và quy tắc riêng (xem mục 9).

## 2. Từ seed đến tính tái lập

`java.util.Random` là PRNG. Nó tạo chuỗi các giá trị từ trạng thái nội bộ, nên hai instance `Random` độc lập có cùng seed sẽ cho cùng chuỗi nếu thực hiện cùng các lời gọi theo cùng thứ tự.

~~~java
import java.util.Random;

Random first = new Random(2026L);
Random second = new Random(2026L);

System.out.println(first.nextInt(10) == second.nextInt(10)); // true
System.out.println(first.nextInt(10) == second.nextInt(10)); // true
~~~

Ở đây seed `2026L` không làm hai đối tượng dùng chung trạng thái; nó khởi tạo trạng thái tương đương. Hai phép gọi tuần tự tạo hai cặp giá trị trùng nhau. Không cần ghi nhớ giá trị cụ thể để hiểu cơ chế.

Điều kiện để tái lập hữu ích:

- Cùng **thuật toán**: `Random`, `SplittableRandom` hoặc một algorithm của `RandomGeneratorFactory` không nhất thiết sinh cùng chuỗi dù seed giống nhau.
- Cùng **seed**, số lần gọi và phương thức được gọi: thêm một lời gọi `nextInt()` trước bước cần test sẽ làm lệch các giá trị tiếp theo.
- Cùng cách phân phối giá trị: `nextInt(6)` và `nextInt()` không có nghĩa như nhau.
- Không có nhiều luồng tranh nhau gọi vào cùng một nguồn theo thứ tự không xác định.

Seed là công cụ tái hiện lỗi rất hữu ích: ghi lại seed cùng tên thuật toán, cấu hình kiểm thử và dữ liệu đầu vào. Nếu testcase thất bại ở seed cụ thể, chạy lại với đúng thông tin đó giúp điều tra.

**Không nên đánh đồng tính tái lập với tính dự đoán nghiệp vụ.** Một seed cố định giúp lặp lại chuỗi, nhưng một test quá phụ thuộc vào “giá trị lần gọi thứ 37 phải là 6” dễ bị hỏng khi code thêm một lần rút số ngẫu nhiên hợp lệ.

## 3. Java 17+: truyền `RandomGenerator` vào logic nghiệp vụ

Java 17 cung cấp interface `java.util.random.RandomGenerator`. `java.util.Random` là một implementation của interface này; vì thế có thể nhận dependency qua interface, trong khi nơi khởi tạo quyết định dùng implementation nào.

Ví dụ:

~~~java
import java.util.Objects;
import java.util.random.RandomGenerator;

public final class Dice {
    private final RandomGenerator random;

    public Dice(RandomGenerator random) {
        this.random = Objects.requireNonNull(random, "random");
    }

    public int roll() {
        return random.nextInt(6) + 1;
    }
}
~~~

Đây là lớp độc lập minh họa; ở mục 7 có chương trình Java hoàn chỉnh chứa nhiều bài test. `random.nextInt(6)` trả một `int` trong khoảng **0 đến 5**; cộng thêm 1 để tạo giá trị **1 đến 6**. Việc dùng overload có bound giúp tránh modulo thủ công dễ tạo phân phối lệch hoặc số âm.

Lợi ích của dependency injection:

- Production có thể truyền một nguồn PRNG được lựa chọn theo chính sách ứng dụng.
- Unit test truyền một `Random` có seed cố định để tái hiện một chuỗi.
- Unit test cần nhánh cụ thể truyền một nguồn giả (*fake*) để trả đúng những giá trị đã chọn.
- Lớp nghiệp vụ chỉ diễn đạt cách sử dụng số ngẫu nhiên, không quyết định cách khởi tạo seed và không cần biết thuật toán.

Ví dụ cách dùng:

~~~java
// Ví dụ trong phạm vi một phương thức:
Dice productionDice = new Dice(new java.util.Random());
Dice repeatableDice = new Dice(new java.util.Random(2026L));
~~~

Có thể sử dụng `RandomGenerator.getDefault()` khi chính sách ứng dụng chấp nhận thuật toán mặc định. Nếu cần tái lập ổn định trên môi trường khác nhau, **nêu rõ implementation/algorithm và seed**; mặc định của môi trường không phải một hợp đồng cố định về chuỗi.

Nhiều ứng dụng còn cần truyền *factory* tạo RNG cho mỗi phiên hoặc mỗi worker, thay vì một instance chung. Quyết định này đặc biệt quan trọng khi có nhiều luồng và cần tái lập thứ tự tiêu thụ.

## 4. Kiểm thử bằng seed: nên khẳng định điều gì?

### Kiểm tra cùng seed tạo cùng chuỗi

Một test hợp lý so sánh hai thực thể độc lập dùng cùng seed, cùng số bước:

~~~java
import java.util.Arrays;
import java.util.Random;

Random a = new Random(2026L);
Random b = new Random(2026L);

int[] sequenceA = new int[10];
int[] sequenceB = new int[10];

for (int i = 0; i < sequenceA.length; i++) {
    sequenceA[i] = a.nextInt(100);
    sequenceB[i] = b.nextInt(100);
}

System.out.println(Arrays.equals(sequenceA, sequenceB)); // true
~~~

Test chứng minh cơ chế tái lập trong cùng thuật toán và cùng lời gọi. Nếu cần kiểm thử **logic nghiệp vụ**, ta nên assert điều kiện nghiệp vụ thực sự quan tâm hơn là chỉ kiểm tra PRNG của JDK.

Ví dụ với lớp `Dice`, có thể chạy nhiều lượt và assert `1 <= roll && roll <= 6`. Thử 10.000 lần tăng khả năng phát hiện lỗi bound hoặc phép biến đổi, nhưng vẫn không phải chứng minh phân phối hoàn toàn đồng đều.

### Tái hiện một lỗi theo seed

Giả sử một pipeline gặp lỗi ở seed `58723L`. Lưu lại:

~~~text
generator: java.util.Random
seed: 58723
scenario: choose promotion after reading customer category
input fixture: customer-group-A
~~~

Thông tin seed **một mình** có thể không đủ nếu thuật toán, thứ tự lời gọi hoặc tập dữ liệu đã đổi. Một fixture tái hiện đáng tin cần ghi cả quy tắc rút số và điều kiện của test.

Không đặt seed cố định trong hệ thống production nếu mục tiêu là tạo hành vi khó dự đoán. Seed cố định dành cho kiểm thử, mô phỏng cần tái lập hoặc chức năng nghiệp vụ có yêu cầu rõ ràng về chuỗi giả ngẫu nhiên.

### Hạn chế của seeded tests

Test chỉ dùng seed có thể không chạm được trường hợp cần thiết, ví dụ rút đúng 0 hoặc giá trị biên lớn nhất. “Chạy 1.000 lần rồi hy vọng gặp điều kiện đó” tạo test khó đọc và có nguy cơ flaky. Để kiểm tra một nhánh xác định, hãy truyền nguồn giả với kết quả được kiểm soát.

## 5. Kiểm thử bằng nguồn được truyền vào: tạo fake có kịch bản

Giả sử ứng dụng có:

~~~java
boolean shouldSample(int percent) {
    return random.nextInt(100) < percent;
}
~~~

Với `percent = 0`, kết quả luôn `false`; với `percent = 100`, kết quả luôn `true`; với `percent = 25`, các giá trị rút trong khoảng 0–24 làm kết quả `true`, còn 25–99 cho `false`.

Thay vì đoán seed nào sẽ sinh 24 hoặc 25 đúng vị trí, một fake có thể cung cấp danh sách giá trị rõ ràng. Vì `Random` implement `RandomGenerator`, ta có thể kế thừa `Random` và override `nextInt(int bound)` cho trường hợp đang kiểm thử:

~~~java
import java.util.Random;

final class ScriptedRandom extends Random {
    private final int[] values;
    private int cursor;

    ScriptedRandom(int... values) {
        super(0L);
        this.values = values.clone();
    }

    @Override
    public int nextInt(int bound) {
        if (bound <= 0) {
            throw new IllegalArgumentException("bound must be positive");
        }
        if (cursor >= values.length) {
            throw new AssertionError("Scripted values exhausted");
        }
        int value = values[cursor++];
        if (value < 0 || value >= bound) {
            throw new AssertionError(
                    "Invalid scripted value " + value
                            + " for bound " + bound);
        }
        return value;
    }

    int calls() {
        return cursor;
    }
}
~~~

Đây là một fake **chỉ dành cho test**. Nó kiểm tra bound để phát hiện code sản phẩm gọi API với khoảng không mong muốn. Nó không mô phỏng toàn bộ hành vi của `Random`, không được dùng làm PRNG production, và chỉ thay thế chính xác lời gọi `nextInt(int)` mà code nghiệp vụ thực sự sử dụng.

Nếu code sản phẩm thay sang `nextLong()` hoặc phương thức RNG khác, fake phải hỗ trợ lời gọi đó hoặc thiết kế một interface domain hẹp hơn, ví dụ:

~~~java
@FunctionalInterface
interface IndexSource {
    int nextIndex(int exclusiveUpperBound);
}
~~~

Trong thiết kế domain, truyền `IndexSource` thường tốt nếu service chỉ cần rút index. Test có thể truyền lambda `bound -> 0` để luôn chọn phần tử đầu; production truyền `random::nextInt`. Interface hẹp giảm sự phụ thuộc vào chi tiết toàn bộ RNG.

**Chọn mức trừu tượng phù hợp:** dùng `RandomGenerator` khi logic cần các thao tác RNG phổ biến; dùng interface domain nhỏ khi muốn chỉ cho phép một hoặc vài thao tác ngẫu nhiên có ý nghĩa nghiệp vụ.

## 6. Những nhánh cần ép bằng fake

Giả sử method `chooseIndex(int size)` chọn index trong `[0, size)` và method `shouldSample(int percent)` nhận phần trăm từ 0 đến 100.

| Trường hợp | Giá trị fake trả | Điều cần assert |
| --- | ---: | --- |
| `chooseIndex(6)` | `0` | Chọn phần tử đầu |
| `chooseIndex(6)` | `5` | Chọn phần tử cuối |
| `shouldSample(25)` | `24` | `true` |
| `shouldSample(25)` | `25` | `false` |
| `shouldSample(0)` | `0` | `false` |
| `shouldSample(100)` | `99` | `true` |
| `chooseIndex(0)` | Không gọi nguồn | Ném `IllegalArgumentException` trước khi rút |

Với fake, các kiểm thử này **không phụ thuộc vào xác suất** và nên cho kết quả giống nhau ở mọi lần chạy.

Phải phân biệt **giới hạn inclusive/exclusive**. Với `nextInt(bound)`, bound là **exclusive**: `nextInt(6)` không thể trả 6. Đối với `RandomGenerator.nextInt(origin, bound)`, origin là inclusive, bound là exclusive. Tránh tự dùng phép `Math.abs(random.nextInt()) % size`: `Math.abs(Integer.MIN_VALUE)` vẫn âm và phép lấy dư có thể gây phân phối lệch.

## 7. Chương trình Java 17+ chạy độc lập

Tạo tệp `RandomSourceTestingDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;
import java.util.random.RandomGenerator;

public class RandomSourceTestingDemo {

    static final class Picker {
        private final RandomGenerator random;

        Picker(RandomGenerator random) {
            this.random = Objects.requireNonNull(random, "random");
        }

        int chooseIndex(int size) {
            if (size <= 0) {
                throw new IllegalArgumentException("size must be positive");
            }
            return random.nextInt(size);
        }

        int rollDie() {
            return random.nextInt(6) + 1;
        }

        boolean shouldSample(int percent) {
            if (percent < 0 || percent > 100) {
                throw new IllegalArgumentException(
                        "percent must be between 0 and 100");
            }
            return random.nextInt(100) < percent;
        }
    }

    static final class ScriptedRandom extends Random {
        private final int[] values;
        private int cursor;

        ScriptedRandom(int... values) {
            super(0L);
            this.values = values.clone();
        }

        @Override
        public int nextInt(int bound) {
            if (bound <= 0) {
                throw new IllegalArgumentException("Invalid bound");
            }
            if (cursor >= values.length) {
                throw new AssertionError("No more scripted values");
            }
            int value = values[cursor++];
            if (value < 0 || value >= bound) {
                throw new AssertionError("Scripted value outside bound");
            }
            return value;
        }

        int calls() {
            return cursor;
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        // Hai PRNG cùng seed, cùng thứ tự gọi, tạo cùng chuỗi.
        Picker first = new Picker(new Random(2026L));
        Picker second = new Picker(new Random(2026L));
        int[] valuesA = new int[5];
        int[] valuesB = new int[5];

        for (int i = 0; i < 5; i++) {
            valuesA[i] = first.chooseIndex(10);
            valuesB[i] = second.chooseIndex(10);
        }

        boolean reproducible = Arrays.equals(valuesA, valuesB);
        require(reproducible, "Seeded sequences must match");
        System.out.println("same seed, same sequence: " + reproducible);

        // Fake ép giá trị đầu, cuối và hai nhánh phần trăm.
        ScriptedRandom scripted = new ScriptedRandom(0, 5, 0, 99);
        Picker predictable = new Picker(scripted);

        int firstIndex = predictable.chooseIndex(6);
        int lastIndex = predictable.chooseIndex(6);
        boolean zeroPercent = predictable.shouldSample(0);
        boolean fullPercent = predictable.shouldSample(100);

        require(firstIndex == 0, "Expected first index");
        require(lastIndex == 5, "Expected last index");
        require(!zeroPercent, "0 percent must be false");
        require(fullPercent, "100 percent must be true");
        require(scripted.calls() == 4, "Wrong number of random draws");

        System.out.println("scripted first index: " + firstIndex);
        System.out.println("scripted last index: " + lastIndex);
        System.out.println("sample at 0%: " + zeroPercent);
        System.out.println("sample at 100%: " + fullPercent);
        System.out.println("scripted calls: " + scripted.calls());

        // Kiểm tra bất biến theo khoảng giá trị, không hard-code chuỗi.
        Picker die = new Picker(new Random(7L));
        boolean inRange = true;
        for (int i = 0; i < 10_000; i++) {
            int rolled = die.rollDie();
            if (rolled < 1 || rolled > 6) {
                inRange = false;
                break;
            }
        }
        require(inRange, "A die roll must be between 1 and 6");
        System.out.println("die range verified: " + inRange);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RandomSourceTestingDemo.java
java RandomSourceTestingDemo
~~~

Stdout:

~~~text
same seed, same sequence: true
scripted first index: 0
scripted last index: 5
sample at 0%: false
sample at 100%: true
scripted calls: 4
die range verified: true
~~~

Đoạn fake được test bằng giá trị `0, 5, 0, 99` tương ứng các bound `6, 6, 100, 100`. Mỗi giá trị đều nằm trong khoảng hợp lệ. Test cũng kiểm tra chính xác số lần tiêu thụ RNG để phát hiện thay đổi bất ngờ trong cách code chọn số.

Bài học về cấu trúc test:

- **Seeded PRNG** kiểm tra khả năng tái lập một chuỗi qua cùng thuật toán và thứ tự gọi.
- **Scripted fake** kiểm tra nhánh cụ thể và các điểm biên một cách quyết định.
- **Property/bound test** kiểm tra điều kiện đúng với nhiều lần lấy mẫu, không yêu cầu một chuỗi ngẫu nhiên cụ thể.

Cả ba có vai trò khác nhau; không nên dùng một test seeded duy nhất để thay thế mọi kiểm thử nhánh.

## 8. Thiết kế unit test JUnit 5

Với dự án dùng JUnit Jupiter, có thể viết test theo hướng sau. Đây là **đoạn trích** giả định lớp `Picker` và `ScriptedRandom` của chương trình ở mục 7 là các kiểu mà test có thể truy cập, ví dụ đặt test trong cùng package hoặc chuyển chúng sang class phù hợp:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Random;
import org.junit.jupiter.api.Test;

class PickerTest {
    @Test
    void sameSeedReproducesDraws() {
        var a = new RandomSourceTestingDemo.Picker(new Random(42L));
        var b = new RandomSourceTestingDemo.Picker(new Random(42L));
        for (int i = 0; i < 100; i++) {
            assertEquals(a.chooseIndex(1_000), b.chooseIndex(1_000));
        }
    }

    @Test
    void fakeForcesBoundaryBranches() {
        var fake = new RandomSourceTestingDemo.ScriptedRandom(0, 5);
        var picker = new RandomSourceTestingDemo.Picker(fake);
        assertEquals(0, picker.chooseIndex(6));
        assertEquals(5, picker.chooseIndex(6));
        assertEquals(2, fake.calls());
    }

    @Test
    void invalidSizeRejectedBeforeDraw() {
        var fake = new RandomSourceTestingDemo.ScriptedRandom(0);
        var picker = new RandomSourceTestingDemo.Picker(fake);
        assertThrows(IllegalArgumentException.class,
                () -> picker.chooseIndex(0));
        assertEquals(0, fake.calls());
    }

    @Test
    void everyDieResultStaysInsideDomain() {
        var picker = new RandomSourceTestingDemo.Picker(
                new Random(1001L));
        for (int i = 0; i < 10_000; i++) {
            int rolled = picker.rollDie();
            assertTrue(rolled >= 1 && rolled <= 6);
        }
    }
}
~~~

Đoạn JUnit ở trên cần dependency JUnit Jupiter trong build và được chạy qua test runner (Gradle/Maven/IDE) của dự án. Nó **không** phải một chương trình chỉ dùng JDK để chạy bằng lệnh `java PickerTest`.

Nếu bản production chỉ định một PRNG/thuật toán khác, tạo constructor/factory phù hợp để test chủ động chọn chính implementation ấy. Không so sánh trực tiếp các chuỗi từ hai thuật toán khác nhau chỉ vì chúng được khởi tạo cùng seed.

## 9. Phân biệt PRNG kiểm thử với ngẫu nhiên bảo mật

`Random`, `SplittableRandom` và nhiều implementation của `RandomGenerator` là nguồn **giả ngẫu nhiên không dùng cho mật mã**. Seed có thể khiến chuỗi lặp lại và có thể bị dự đoán; đó là điều hữu ích cho test mô phỏng nhưng nguy hiểm với token đăng nhập, mật khẩu ngẫu nhiên, mã khôi phục, khóa hoặc giá trị cần bí mật.

Với mục đích bảo mật, sử dụng `java.security.SecureRandom` theo hướng dẫn bảo mật và thuật toán/provider phù hợp:

~~~java
import java.security.SecureRandom;

SecureRandom secure = new SecureRandom();
byte[] token = new byte[32];
secure.nextBytes(token);
~~~

**Không cố định seed của `SecureRandom` trong production** để mong tạo token lặp lại. `SecureRandom.setSeed(...)` không phải giao diện bảo đảm “đặt trạng thái thành đúng seed để phát lại cùng chuỗi” như giả định đơn giản với `Random`; chi tiết còn tùy provider và cách khởi tạo. Khi kiểm thử code liên quan bảo mật, tách logic xử lý token/nonce khỏi nguồn tạo byte: test có thể tiêm dữ liệu giả định **chỉ trong môi trường test** để kiểm tra format, validation, đường lỗi; production vẫn dùng nguồn bảo mật.

Không thay `SecureRandom` bằng `new Random(seed)` chỉ để test dễ hơn. Nếu hệ thống cần tính khó dự đoán, đó là một yêu cầu chức năng quan trọng cần giữ nguyên.

## 10. Seed, nguồn chia sẻ và nhiều luồng

Một nguồn được tạo từ seed có thể sinh chuỗi ổn định khi chạy tuần tự, nhưng **cùng seed không bảo đảm cùng kết quả nghiệp vụ nếu thứ tự các luồng tiêu thụ thay đổi**.

Ví dụ nhiều thread gọi cùng một `Random`:

- Một lần chạy: thread A rút giá trị thứ nhất, B rút thứ hai.
- Lần chạy khác: B rút giá trị thứ nhất, A rút thứ hai.

Ngay cả khi PRNG tạo cùng một chuỗi tổng thể, kết quả gắn với từng thread hoặc từng bản ghi có thể khác. Tranh chấp cũng ảnh hưởng hiệu năng. Các API như `ThreadLocalRandom.current()` cung cấp RNG theo thread, nhưng `ThreadLocalRandom.setSeed(long)` không hỗ trợ đặt seed để phát lại theo cách quen thuộc; nó ném `UnsupportedOperationException`.

Nếu bài toán mô phỏng song song phải tái lập ổn định, có thể:

1. Xác định một quy tắc gán seed theo **định danh công việc** được giữ ổn định, ví dụ cùng mã task và một master seed được lưu.
2. Tạo RNG riêng cho mỗi task/partition từ chính sách đó.
3. Đảm bảo mỗi task thực hiện cùng thứ tự rút số hoặc thiết kế cách rút không phụ thuộc thứ tự.
4. Nếu dùng `SplittableRandom.split()` hoặc generator hỗ trợ split, ghi nhận quy tắc phân chia; thay đổi thứ tự split có thể làm thay đổi chuỗi của từng task.

Không nên giả định nhiều thread chia sẻ một instance tùy ý đều thread-safe: hãy kiểm tra hợp đồng của implementation được chọn. Ngay cả khi implementation hỗ trợ gọi đồng thời, **tính tái lập kết quả theo nhiệm vụ** vẫn là vấn đề riêng.

## 11. Những kiểu test gây flaky hoặc che lỗi

### Sai 1: assert một kết quả cụ thể của RNG thật không seed

~~~java
int x = new Random().nextInt(6) + 1;
// Sai: assert x == 4. Điều này chỉ đúng ngẫu nhiên.
~~~

Thay bằng test bất biến của output hoặc fake ép nhánh.

### Sai 2: phụ thuộc một chuỗi cố định không cần thiết

Một test mã hóa sẵn 100 kết quả PRNG cho một chức năng chỉ yêu cầu nằm trong `[0, 6)` sẽ dễ hỏng khi đổi algorithm hoặc thêm một lần rút số. Nếu thực sự cần đối chiếu thuật toán PRNG, chuỗi chuẩn cố định có thể là *golden vectors* hữu ích. Còn với nghiệp vụ, ưu tiên assert kết quả và các nhánh nghiệp vụ.

### Sai 3: tạo RNG trong method không thể thay thế

~~~java
int pick() {
    return new Random().nextInt(10);
}
~~~

Không có cách đơn giản để tiêm fake vào method này. Chuyển thành dependency qua constructor, tham số method hoặc factory nếu cần kiểm soát vòng đời.

### Sai 4: reset seed giữa các lời gọi

~~~java
Random random = new Random(42L);
for (int i = 0; i < 5; i++) {
    random.setSeed(42L); // lặp lại trạng thái khởi đầu
    System.out.println(random.nextInt(10));
}
~~~

Đặt lại seed trước **mỗi lần rút** sẽ tái sử dụng trạng thái ban đầu và có thể tạo cùng giá trị lặp đi lặp lại, không giống với một chuỗi rút liên tiếp. Test tái lập thường đặt seed **một lần khi tạo nguồn cho từng test**.

### Sai 5: chia sẻ instance giữa các test

Nếu nhiều unit test cùng dùng một `static Random`, test này làm thay đổi trạng thái mà test khác sẽ đọc. Thứ tự chạy hoặc parallel execution có thể làm kết quả khác nhau. Mỗi test nên sở hữu một nguồn riêng (hoặc fixture riêng) và seed rõ ràng.

### Sai 6: dùng thống kê sơ sài để “chứng minh ngẫu nhiên”

Kiểm tra rằng 10 lần tung xúc xắc phải xuất hiện đủ cả 6 mặt là test flaky ngay cả với PRNG chính xác. Phép thử thống kê phải có giả thuyết, kích thước mẫu và ngưỡng sai số thích hợp; không dùng nó làm unit test bắt buộc nếu chưa phân tích xác suất sai báo. Kiểm thử logic biến đổi/bound với fake và kiểm thử thống kê đặc thù là hai nhiệm vụ khác nhau.

## 12. Mẫu lựa chọn chiến lược test

| Mục đích | Cách phù hợp | Điều cần khẳng định |
| --- | --- | --- |
| Tái hiện bug cụ thể | Seed, algorithm, fixture và thứ tự rút được ghi lại | Cùng bối cảnh tái hiện bug |
| Chọn nhánh đầu/cuối | Fake có kịch bản | Code xử lý đúng giá trị 0 và bound−1 |
| Đảm bảo output trong miền | Kiểm tra invariant/property | Không ra ngoài miền giá trị |
| Test phân phối | Thử nghiệm thống kê riêng với ngưỡng có cơ sở | Sai lệch nằm trong ngưỡng đã đặt |
| Test concurrency | RNG/seed cho từng task và đồng bộ kịch bản | Tính đúng đắn độc lập lịch chạy |
| Test luồng bảo mật | Tiêm dữ liệu giả ở ranh giới logic, production dùng `SecureRandom` | Format, xử lý lỗi và yêu cầu an toàn |

Không cần ép mọi thành phần của ứng dụng nhận cả interface `RandomGenerator` nếu component chỉ cần một quyết định rất hẹp. Có thể truyền một interface domain riêng như `IndexSource` hoặc `BooleanDecision` để unit test ngắn hơn và giảm sự ràng buộc vào chi tiết PRNG.

## 13. Tự kiểm tra

**Câu 1.** Hai instance `new Random(123L)` có chắc chắn cho cùng giá trị trong 20 lần gọi `nextInt(10)` khi được gọi theo cùng thứ tự không? Nếu một instance bị gọi thêm `nextLong()` trước lượt 10 thì sao?

**Câu 2.** Tại sao không nên kiểm tra `rollDie() == 6` bằng cách gọi 10 lần rồi hy vọng có giá trị 6? Hãy nêu một cách chủ động kiểm tra nhánh 6.

**Câu 3.** Một phương thức quyết định lấy mẫu bằng `random.nextInt(100) < 25`. Fake phải trả những giá trị nào để kiểm tra đúng cả hai phía của biên?

**Câu 4.** Vì sao không nên để nhiều test dùng chung một `static Random`, dù nó được khởi tạo với seed cố định?

**Câu 5.** Vì sao `SecureRandom` không được thay thế bằng `Random(42L)` trong chức năng tạo token production?

**Câu 6.** Nếu một lần chạy simulation song song và lần chạy kế tiếp có cùng master seed nhưng thứ tự phân chia công việc khác, kết quả của từng task có chắc chắn giống nhau không?

### Đáp án

1. Có, khi cùng `java.util.Random`, cùng seed và cùng chuỗi lời gọi. Nếu một nguồn tiêu thụ thêm giá trị, các lượt tiếp theo không còn tương ứng theo vị trí cũ.
2. Đó là kiểm thử dựa vào may rủi; có thể cung cấp fake cho `nextInt(6)` trả 5, rồi assert kết quả `rollDie()` là 6.
3. Fake trả 24 cho nhánh `true` và 25 cho nhánh `false`; cả hai đều nằm trong `[0,100)`.
4. Mỗi test tiêu thụ trạng thái chung nên thứ tự chạy và chạy song song ảnh hưởng dữ liệu ngẫu nhiên.
5. `Random` là PRNG thông thường và chuỗi có seed cố định có thể dự đoán, không đáp ứng mục đích bảo mật.
6. Không. Tính tái lập còn cần quy tắc gán nguồn/seed, thứ tự split, thứ tự tiêu thụ và ánh xạ công việc ổn định.

**Điểm cần nhớ:** seed cố định giúp **tái hiện một chuỗi**, còn dependency injection giúp **kiểm soát chính xác nhánh nghiệp vụ**. Kết hợp seeded test, scripted fake và kiểm tra bất biến để tạo test rõ ràng, ổn định; phân biệt hoàn toàn với yêu cầu sinh số ngẫu nhiên có tính bảo mật.
