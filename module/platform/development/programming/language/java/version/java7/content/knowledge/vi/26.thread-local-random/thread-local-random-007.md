# ThreadLocalRandom — Chọn cách kiểm thử khi không thể điều khiển seed

## 1. Bài toán: không thể tạo lại cùng dãy ngẫu nhiên

Một hệ thống Java dùng `ThreadLocalRandom.current().nextInt(100, 200)` để chọn một bucket, chia traffic thử nghiệm, sinh thời gian jitter hoặc lựa chọn một phương án trong số nhiều kết quả hợp lệ. Người viết test muốn kiểm tra tính đúng đắn, nhưng mỗi lần chạy chương trình lại tạo ra giá trị khác nhau. Thử gọi `setSeed(123)` để làm kết quả cố định thì nhận `UnsupportedOperationException`.

Đây là **hành vi đúng theo thiết kế**, không phải lỗi của JDK. `java.util.concurrent.ThreadLocalRandom` là bộ sinh giả ngẫu nhiên **gắn với thread hiện tại**, được khởi tạo bằng seed nội bộ và **không hỗ trợ đặt lại seed qua API công khai**. Mục tiêu chính là giảm tranh chấp khi nhiều threads cần số ngẫu nhiên độc lập, không phải tạo một nguồn dãy số dễ phát lại trong unit test.

Vì vậy câu hỏi thực tế không phải “làm sao ép `ThreadLocalRandom` nhận seed bằng mọi giá?”, mà là:

- Điều gì trong nghiệp vụ **thực sự cần kiểm chứng**?
- Có thể kiểm tra **hợp đồng kết quả** mà không biết trước một số cụ thể không?
- Có cần **tách nguồn random khỏi logic** để unit test kiểm soát được từng nhánh không?
- Khi nào nên dùng một PRNG khác hỗ trợ seed để tái hiện lỗi?
- Những phép kiểm tra xác suất nào dễ trở thành **flaky test**, và cần cô lập chúng ra sao?

**Kết luận trước:** Với `ThreadLocalRandom`, hãy kiểm thử bằng **invariants, thuộc tính hợp lệ và các nhánh logic được điều khiển qua dependency injection**, thay vì khẳng định dãy số bằng một seed không được phép đặt. Khi thật sự cần tái hiện chuỗi, dùng bộ sinh **có seed và thuật toán xác định**, ví dụ `java.util.Random(seed)` hoặc `SplittableRandom(seed)`, hoặc qua interface `RandomGenerator` trong Java 17+.

`ThreadLocalRandom` có từ **Java 7** và vẫn là API phổ biến trong Java hiện đại. `SplittableRandom` có từ Java 8, còn `RandomGenerator` từ Java 17. Các ví dụ chạy trên Java 17; không dùng API bị deprecated hoặc kỹ thuật can thiệp private/internal JDK.

## 2. Hiểu đúng cơ chế ThreadLocalRandom

`ThreadLocalRandom` là một lớp kế thừa `java.util.Random` và được thiết kế để sử dụng từ thread hiện tại:

```java
int selected = java.util.concurrent.ThreadLocalRandom
        .current().nextInt(10, 20);
```

Trong đoạn mã này, `selected` thuộc khoảng **[10,20)**: gồm 10 nhưng **không** gồm 20. Mỗi lần gọi có thể cho một giá trị khác; nếu chạy lại test, không được giả định thứ tự các giá trị giống lần trước.

### 2.1. Vì sao không thể setSeed?

Đoạn sau **biên dịch** nhưng **ném lỗi ở runtime**:

```java
import java.util.concurrent.ThreadLocalRandom;

ThreadLocalRandom.current().setSeed(2026L);
```

`setSeed(long)` trong `ThreadLocalRandom` luôn ném `UnsupportedOperationException`. Đây là cam kết của Javadoc Java SE 17 và các JDK hiện đại, không phải một tính năng bị tắt tạm thời bằng cấu hình test.

Một số người thấy `ThreadLocalRandom` kế thừa `Random` rồi suy rằng mọi API của `Random` có semantics giống nhau. Đây là một ví dụ điển hình về **override thay đổi khả năng thao tác seed**: signature vẫn hiện diện, nhưng việc đổi seed bị từ chối.

### 2.2. Thread-local không có nghĩa “mỗi request” hoặc “mỗi task”

`ThreadLocalRandom.current()` dùng generator liên quan đến **thread đang chạy**, không tự tạo state mới cho từng HTTP request, từng `Runnable` hay từng `CompletableFuture`.

Trong thread pool:

- Nhiều tasks chạy lần lượt trên **cùng một worker thread** có thể dùng cùng trạng thái RNG của thread.
- Một logical request chuyển qua nhiều threads có thể gọi `current()` từ những thread khác nhau.
- Thứ tự scheduling ảnh hưởng thứ tự tiêu thụ ngẫu nhiên và kết quả quan sát.
- Không dùng thứ tự output giữa các worker để khẳng định tính đúng đắn.

Cách gọi thường được khuyến nghị:

```java
int value = ThreadLocalRandom.current().nextInt(100);
```

**Đừng lấy một `ThreadLocalRandom` từ worker A rồi truyền reference cho worker B để cùng dùng.** Javadoc nêu rõ phương thức của instance nên chỉ được gọi bởi thread hiện tại; dùng `current()` tại nơi cần trên chính worker đó.

### 2.3. Đây không phải nguồn ngẫu nhiên bảo mật

`ThreadLocalRandom` là **pseudorandom generator không bảo mật mật mã**. Không dùng để sinh session token, mật khẩu một lần, reset-token hoặc bí mật cần chống đoán.

Khi cần tính bảo mật, dùng `java.security.SecureRandom`, đồng thời kiểm thử theo những đặc điểm bảo mật có thể xác minh được thay vì giả định output bí mật phải khớp một chuỗi cố định.

**Thiết lập property `java.util.secureRandomSeed` không biến ThreadLocalRandom thành API có thể seed thủ công**, cũng không làm nó thích hợp cho secret generation.

## 3. Chọn test theo tầng, không cố định con số ngẫu nhiên

| Tầng kiểm thử | Điều cần chứng minh | Phương pháp phù hợp |
| --- | --- | --- |
| Unit test tính toán thuần | Đúng phân nhánh, mapping, xử lý sai input | Inject fake supplier trả giá trị được chọn trước |
| Unit test logic phụ thuộc nguồn random | Các bước tiêu thụ random và output phù hợp | Inject `RandomGenerator` hoặc `IntSupplier` |
| Kiểm tra hợp đồng của `ThreadLocalRandom` | Range, bound-exclusive, exception | Property/invariant tests qua nhiều mẫu thực |
| Integration/concurrency | Mọi worker lấy số trong phạm vi hợp lệ | Mỗi thread tự gọi `ThreadLocalRandom.current()` |
| Regression tái hiện lỗi | Chạy lại chuỗi như cũ | `new Random(seed)` hoặc generator có thuật toán định danh |
| Statistical test | Nghi ngờ bias, mô hình phân phối | Bộ test thống kê riêng, số mẫu và ngưỡng có thiết kế |
| Security test | Tính không dự đoán được của secret | `SecureRandom`, review threat model/crypto controls |

**Không có một assert duy nhất phù hợp cho tất cả các tầng.** Test chỉ dùng output ngẫu nhiên thực để kiểm tra logic phức tạp sẽ khó tái hiện lỗi và có thể bỏ sót các nhánh hiếm.

### 3.1. Ba chiến lược ưu tiên

1. **Kiểm tra bất biến** (*invariants*): với `nextInt(origin,bound)`, assert `origin <= value && value < bound` cho mọi lần lấy; test thêm trường hợp tham số sai.
2. **Kiểm soát dependency** (*dependency injection*): chuyển logic quyết định ra khỏi việc gọi RNG trực tiếp, inject một nguồn số trả các giá trị cụ thể để thử từng nhánh.
3. **Bộ sinh có seed dành cho test có tính tái hiện**: dùng `Random(seed)`, `SplittableRandom(seed)` hoặc `RandomGenerator` cụ thể, bảo đảm cùng thứ tự lời gọi; ghi cả thuật toán/seed khi cần debug.

Nên làm cả ba: tách business logic để deterministic, đồng thời có một bài kiểm tra nhỏ rằng adapter production sử dụng `ThreadLocalRandom` tuân thủ hợp đồng API.

## 4. Kiểm thử invariant: kiểm tra điều chắc chắn đúng

Với:

```java
int value = ThreadLocalRandom.current().nextInt(-5, 8);
```

Hợp đồng kết quả là `-5 <= value < 8`, không phải `value == 3` hoặc bất kỳ con số cụ thể nào.

Ví dụ kiểm tra:

```java
for (int i = 0; i < 10_000; i++) {
    int value = ThreadLocalRandom.current().nextInt(-5, 8);
    if (value < -5 || value >= 8) {
        throw new AssertionError("Out of range");
    }
}
```

Đây là đoạn mã có thể đặt trong một phương thức Java; nó không in một dãy ngẫu nhiên khó dự đoán. Nếu tất cả lần gọi hợp lệ, vòng lặp hoàn tất.

### 4.1. Kiểm tra biên dạng [origin, bound)

| API | Khoảng hợp lệ | Lưu ý |
| --- | --- | --- |
| `nextInt(bound)` | `0 <= x < bound` | `bound > 0` |
| `nextInt(origin,bound)` | `origin <= x < bound` | `origin < bound` |
| `nextLong(bound)` | `0 <= x < bound` | `bound > 0` |
| `nextLong(origin,bound)` | `origin <= x < bound` | `origin < bound` |
| `nextDouble()` | `0.0 <= x < 1.0` | Không kỳ vọng luôn có 0 |
| `nextDouble(origin,bound)` | `origin <= x < bound` | Các tham số phải hợp lệ theo hợp đồng |

Các khoảng **nửa kín nửa mở** rất dễ bị nhầm. Trong ví dụ `nextInt(1,7)`, giá trị có thể là 1,2,3,4,5,6 — **không phải 7**.

Nếu nghiệp vụ cần giá trị nguyên **bao gồm cả biên trên**, xác định tham số bằng quy tắc đúng và kiểm tra overflow, không cộng 1 mù quáng khi upper bound có thể là `Integer.MAX_VALUE`.

### 4.2. Kiểm thử tham số không hợp lệ

`nextInt(0)` không có số nguyên hợp lệ trong `[0,0)`; `nextInt(5,5)` hoặc `nextInt(10,2)` cũng không có khoảng đúng.

```java
boolean rejected = false;
try {
    ThreadLocalRandom.current().nextInt(5, 5);
} catch (IllegalArgumentException expected) {
    rejected = true;
}
if (!rejected) {
    throw new AssertionError("Expected invalid range");
}
```

Đây là kiểm thử **deterministic**: không phụ thuộc seed hoặc scheduling. Nó kiểm chứng precondition của API, không đòi đo xác suất.

### 4.3. Kiểm thử kiểu đặc biệt

Với các tham số double, hãy chú ý `NaN`, infinity, khoảng không hợp lệ và những quy tắc làm tròn floating-point. Đối với mô hình ứng dụng cần một range thực, **validate dữ liệu đầu vào nghiệp vụ** và kiểm thử exception của API theo Javadoc bản JDK đang dùng. Không dùng một giá trị `double` ngẫu nhiên để test equality chính xác với một số thập phân dạng chuỗi.

### 4.4. Có nên assert đã thấy mọi giá trị?

**Không đưa vào unit test bình thường** một assert như “sau 100 lần gọi phải có đủ cả mười chữ số”. Xác suất rất nhỏ nhưng **không bằng 0** để một kết quả hiếm xuất hiện; đó là flaky test.

Tương tự, không assert hai lần `nextInt` liên tiếp phải khác nhau. Sinh cùng một số hai lần là kết quả hợp lệ của RNG; “số ngẫu nhiên” không đồng nghĩa “không trùng”.

## 5. Tách nguồn ngẫu nhiên bằng IntSupplier

Giả sử dịch vụ quyết định nhóm thí nghiệm dựa trên số từ `0` đến `9`: số dưới 3 thuộc nhóm `EARLY`, các số còn lại thuộc `NORMAL`.

Cách viết khó kiểm thử:

```java
String bucket() {
    int number = ThreadLocalRandom.current().nextInt(0, 10);
    return number < 3 ? "EARLY" : "NORMAL";
}
```

Đây là một method minh họa nằm trong class. Không có cơ chế nào đảm bảo test sẽ sinh số dưới 3 ngay lần gọi mong muốn. Một test gọi hàm 100 lần rồi đợi thấy đủ hai nhánh có thể đột nhiên thất bại khi RNG tạo một chuỗi hiếm.

**Thiết kế tốt hơn: inject một nguồn lấy số**:

```java
import java.util.Objects;
import java.util.function.IntSupplier;

final class BucketService {
    private final IntSupplier draw;

    BucketService(IntSupplier draw) {
        this.draw = Objects.requireNonNull(draw);
    }

    String bucket() {
        int value = draw.getAsInt();
        if (value < 0 || value >= 10) {
            throw new IllegalArgumentException("out of [0, 10)");
        }
        return value < 3 ? "EARLY" : "NORMAL";
    }
}
```

Đây là class minh họa có thể biên dịch khi đặt trong file Java thích hợp.

Trong production:

```java
BucketService service = new BucketService(
        () -> ThreadLocalRandom.current().nextInt(0, 10));
String currentBucket = service.bucket();
```

Trong unit test:

```java
BucketService early = new BucketService(() -> 2);
BucketService normal = new BucketService(() -> 9);

if (!"EARLY".equals(early.bucket())) {
    throw new AssertionError("Early branch");
}
if (!"NORMAL".equals(normal.bucket())) {
    throw new AssertionError("Normal branch");
}
```

### 5.1. Tại sao đây là cách tốt?

- Test **chắc chắn** đi qua mỗi nhánh theo ý muốn.
- Không động tới internal state hoặc seed của `ThreadLocalRandom`.
- Có thể kiểm tra ranh giới 0, 2, 3, 9 và trường hợp lỗi 10.
- Thông điệp lỗi và kết quả test ổn định.
- Production vẫn dùng `ThreadLocalRandom.current()` **trong đúng thread gọi**, qua lambda supplier.
- Cùng một logic có thể kiểm thử dưới nhiều nguồn dữ liệu.

**Tách random khỏi business logic** thường có giá trị lớn hơn mọi mẹo seed.

### 5.2. Đặt trách nhiệm validate đúng chỗ

Nếu `BucketService` nhận `IntSupplier` bất kỳ từ bên ngoài, nó nên kiểm tra giá trị nằm trong khoảng hợp lệ. Đừng tin supplier giả ở test luôn trả giá trị đúng rồi vô tình bỏ qua validation production.

Ngược lại, nếu adapter RNG đã đảm bảo range và domain layer không chấp nhận số ngoài range, có thể định nghĩa một wrapper mạnh hơn như `BucketIndex` và giữ invariant ở constructor. Điều quan trọng là hợp đồng phải được kiểm thử độc lập với kết quả ngẫu nhiên.

### 5.3. Không dùng fake có state chung thiếu đồng bộ

Một fake supplier:

```java
int[] values = {2, 9};
int[] index = {0};
IntSupplier fake = () -> values[index[0]++];
```

Đây là đoạn minh họa: nó có state mutable trong mảng và **không an toàn nếu nhiều thread cùng dùng**. Với unit test tuần tự, fake có thể hợp lệ; với concurrency test, dùng state per thread hoặc synchronization đúng.

Nếu cần kiểm chứng thứ tự call, fake có sequence rõ ràng, assertion số lần tiêu thụ và chính sách khi hết dữ liệu. Không giả định một fake stateful thread-safe chỉ vì được truyền qua `IntSupplier`.

## 6. Dùng RandomGenerator để thay backend RNG khi cần

Trong **Java 17+**, interface `java.util.random.RandomGenerator` cung cấp các phương thức chung `nextInt`, `nextLong`, `nextDouble`. Nhiều nguồn RNG hiện hành cùng triển khai interface này, bao gồm `Random` và `ThreadLocalRandom`.

Thiết kế:

```java
import java.util.Objects;
import java.util.random.RandomGenerator;

final class Picker {
    private final RandomGenerator random;

    Picker(RandomGenerator random) {
        this.random = Objects.requireNonNull(random);
    }

    int choose() {
        return random.nextInt(100, 200);
    }
}
```

Ở production, thay vì cache một instance của `ThreadLocalRandom` từ thread khác, có thể tạo `Picker` trong scope phù hợp hoặc dùng `IntSupplier` lấy `current()` ngay khi cần. **Đừng share một `ThreadLocalRandom` object giữa workers** chỉ vì nó implement `RandomGenerator`.

Trong test deterministic:

```java
import java.util.SplittableRandom;

Picker first = new Picker(new SplittableRandom(2026L));
Picker second = new Picker(new SplittableRandom(2026L));

for (int i = 0; i < 100; i++) {
    if (first.choose() != second.choose()) {
        throw new AssertionError("Same seed, same sequence expected");
    }
}
```

Hai instance **cùng thuật toán và seed**, được gọi **theo cùng thứ tự**, sẽ cho cùng kết quả trong môi trường được kiểm thử. Test không cần hardcode giá trị số cụ thể.

### 6.1. Nếu muốn khả năng phát lại mạnh qua nhiều JDK

`java.util.Random` truyền thống có thuật toán chuẩn được Javadoc quy định để đảm bảo khả năng tái hiện cùng seed và cùng chuỗi lời gọi giữa các implementation Java tương thích. Vì thế nó có thể phù hợp cho một test cần kết quả ổn định dài hạn, dù không phải luôn là lựa chọn tốt nhất về hiệu năng hay thống kê.

`SplittableRandom` là bộ sinh có seed và hữu ích cho các test nội bộ; với nhu cầu regression cực kỳ nghiêm ngặt qua môi trường/JDK, hãy xác định **tên thuật toán, phiên bản và cách tiêu thụ các giá trị**, không chỉ ghi “seed = 2026” mà quên thuật toán.

Với Java 17, `RandomGeneratorFactory` cho phép chọn các thuật toán cụ thể khi cần. Tránh chọn thuật toán mặc định “bất kỳ” rồi kỳ vọng golden sequence bất biến qua mọi JVM hoặc upgrade.

### 6.2. Không đổi nguồn random một cách âm thầm trong production

Nếu hệ thống vốn dùng `ThreadLocalRandom`, chuyển toàn bộ sang một instance `new Random(123)` dùng chung chỉ để test dễ viết có thể thay đổi độ tranh chấp, hiệu năng và sự phân phối giữa các worker.

Ưu tiên **inject source chỉ ở ranh giới cần kiểm soát**. Test dùng seeded generator, còn production dùng lambda gọi `ThreadLocalRandom.current()` hoặc design mỗi worker sở hữu RNG phù hợp.

### 6.3. Vì sao không lấy seed bằng reflection/private fields?

Dựa vào `Unsafe`, reflection vào package nội bộ, static state của `Thread` hoặc các chi tiết implementation không phải API được hỗ trợ có thể thất bại vì module encapsulation, thay đổi JDK, tranh chấp với threads khác và tính khả chuyển thấp.

Đây là hướng **không khuyến nghị**. Nhu cầu có thể tái hiện phải được thiết kế ở API nghiệp vụ thay vì can thiệp nội bộ PRNG.

## 7. Unit test tránh flaky: property trước, exact sequence sau

Hãy phân biệt:

**Test ổn định:**

```java
int x = ThreadLocalRandom.current().nextInt(1, 4);
if (x < 1 || x >= 4) {
    throw new AssertionError("Invalid range");
}
```

**Test không ổn định:**

```java
int x = ThreadLocalRandom.current().nextInt(1, 4);
if (x != 3) {
    throw new AssertionError("Expected a lucky random number");
}
```

Vì `x` có thể là 1, 2 hoặc 3, điều kiện thứ hai có xác suất thất bại lớn dù thư viện hoạt động đúng.

### 7.1. Những khẳng định an toàn

- Mọi giá trị nằm trong khoảng hợp lệ.
- Input không hợp lệ bị từ chối như tài liệu.
- Logic nghiệp vụ trả đúng kết quả **khi supplier được tiêm** những giá trị boundary.
- Không sinh ra `null` khi API trả primitive.
- Tính nhất quán của biến đổi hậu xử lý, ví dụ: lấy modulo hoặc mapping không vi phạm invariant; tốt hơn dùng API bounded trực tiếp thay vì modulo gây bias.
- Trong concurrency test, mỗi worker tự gọi `current()` và không chia sẻ mutable state test bất cẩn.
- Các thao tác độc lập không dùng seed nội bộ như một output contract.

### 7.2. Những khẳng định nên tránh

- “Sau 50 lần random phải có đủ tất cả giá trị”.
- “Hai lần lấy liên tiếp phải khác nhau”.
- “Mọi worker phải tạo dãy hoàn toàn khác nhau”.
- “Phân phối đúng 50/50 sau 20 mẫu”.
- “Dãy ThreadLocalRandom phải giống máy dev”.
- “Mỗi lần chạy test phải in ra một ID khác”.
- “Ngày mai chắc chắn không trùng ID đã tạo hôm nay”.

Số giả ngẫu nhiên có thể trùng nhau; **không dùng RNG như bộ cấp mã duy nhất tuyệt đối**. Nếu bắt buộc uniqueness, cần kiểm tra trùng và cơ chế cấp phát/transaction riêng.

### 7.3. Bảng chọn chiến lược

| Tình huống | Cách kiểm thử |
| --- | --- |
| Chọn 1 trong N bucket | Inject supplier cho từng giá trị biên, assert mapping |
| Chọn delay jitter | Assert delay trong range; inject số để test boundary |
| Thread pool chia tác vụ | Mỗi worker `current()`, assert invariant/concurrency |
| Cần reproduce bug | Tái hiện bằng seed trên `Random`/`SplittableRandom` qua abstraction |
| API dùng bounded int | Test origin inclusive, bound exclusive, invalid range |
| Code sinh random token | Đổi sang `SecureRandom`; test encoding/length/policy, không ghi token raw vào log |
| Kiểm tra uniformity | Statistical test riêng có mức ý nghĩa và số mẫu được thiết kế |
| Kiểm tra business retry | Inject deterministic sequence để đi qua success/fail/timeout branches |

## 8. Kiểm tra phân phối: có nên dùng kiểm định thống kê?

`ThreadLocalRandom.nextInt(bound)` hướng tới phân phối gần đều trên khoảng hợp lệ. Nhưng một sample hữu hạn **luôn có dao động ngẫu nhiên**. Một test đơn giản kiểu:

```java
int n = 1_000;
int[] frequency = new int[10];
for (int i = 0; i < n; i++) {
    frequency[ThreadLocalRandom.current().nextInt(10)]++;
}
for (int count : frequency) {
    if (count != 100) {
        throw new AssertionError("Not exactly uniform");
    }
}
```

**Đây là anti-pattern cố ý**. Phần lớn lượt chạy sẽ không có mỗi bucket đúng 100. Test này kiểm tra một điều không được cam kết.

Một kiểm định thống kê chuyên biệt nên xác định:

1. Giả thuyết null và alternative rõ.
2. Số bucket và số mẫu đủ để kiểm định có ý nghĩa.
3. Mức ý nghĩa `alpha` và khả năng false positive.
4. Test độc lập hoặc điều chỉnh nếu chạy hàng nghìn lần liên tục.
5. Các ảnh hưởng của shared test environment, dữ liệu bị làm tròn, sampling và parallelism.
6. Tiêu chí có thể lặp/debug; ghi aggregate counts và các tham số, **không hứa một lần random production sẽ tái hiện**.

**Không đưa một bài test thống kê có false-positive xác suất nhỏ vào cổng CI bắt buộc mà không có thiết kế quản trị flaky-test.** Test seed-injected và invariant có thể kiểm tra thường xuyên; bài kiểm định thống kê nên tách riêng.

### 8.1. Chi-square không phải bằng chứng mật mã

Ngay cả khi qua một kiểm định histogram, generator **không tự trở thành cryptographically secure**. Tính an toàn của token phụ thuộc khả năng dự đoán state và entropy, không chỉ tần suất từng bucket.

### 8.2. Chi phí test lớn không đồng nghĩa test mạnh

Lặp một triệu lần kiểm tra cùng một invariant giúp tăng mức coverage các giá trị thực, nhưng **không chứng minh thuật toán không bao giờ phát sinh lỗi**. Hãy giữ suite unit có thời lượng phù hợp, thêm property-based/soak test khi cần, và tập trung assert mạnh nhất vào **logic có kiểm soát**.

## 9. Kiểm thử concurrency không điều khiển lịch chạy

Một lợi ích của `ThreadLocalRandom` là mỗi worker dùng random state liên quan thread của mình. Khi chạy trên `ExecutorService`, code nên gọi `ThreadLocalRandom.current()` **trong lambda của mỗi worker**:

```java
var pool = java.util.concurrent.Executors.newFixedThreadPool(4);
try {
    var future = pool.submit(() -> {
        int value = ThreadLocalRandom.current().nextInt(0, 100);
        return value >= 0 && value < 100;
    });
    if (!future.get()) throw new AssertionError("Invalid value");
} finally {
    pool.shutdownNow();
}
```

Đoạn minh họa này nằm trong phương thức có `throws Exception` và sử dụng `ThreadLocalRandom` import đúng. Với hệ thống thật, phải chờ pool `awaitTermination` theo chính sách shutdown.

**Tránh:**

```java
ThreadLocalRandom random = ThreadLocalRandom.current();
pool.submit(() -> random.nextInt(100)); // Không khuyến nghị: lấy ở thread khác.
```

Javadoc nêu phương thức trên instance chỉ nên được gọi bởi thread hiện tại. Lấy `current()` bên trong lambda worker, không capture instance của main thread.

### 9.1. Test không cần dự đoán worker identity

Thread pool có thể tái sử dụng workers. Việc một task chạy ở worker-1 trong lần trước **không có nghĩa** lần sau nó cũng chạy worker-1. Không assert tên thread, seed ngầm hoặc thứ tự output trong kết quả.

### 9.2. Tránh double-random trong assertion

Một lỗi nhỏ nhưng nguy hiểm:

```java
if (ThreadLocalRandom.current().nextInt(10) !=
        ThreadLocalRandom.current().nextInt(10)) {
    // Đây là hai lần lấy khác nhau, không phải cùng một giá trị.
}
```

Nếu cần validate, **lưu kết quả một lần** rồi assert trên biến đó. Test không được lén tiêu thụ thêm số để “so sánh chính nó”, vì sẽ thay đổi trạng thái PRNG và gây khó debug.

## 10. Chương trình Java 17+ hoàn chỉnh, đã chạy

File **`ThreadLocalRandomTestingDemo.java`** dưới đây minh họa các lớp kiểm thử:

1. Gọi `setSeed(42)` và bắt `UnsupportedOperationException` theo hợp đồng.
2. Lấy 50.000 giá trị từ `nextInt(-5,8)` và kiểm tra **mỗi** giá trị thuộc range.
3. Dùng `nextInt(4,4)` kiểm tra `IllegalArgumentException`.
4. Unit test deterministic nhánh `EARLY` và `NORMAL` bằng `IntSupplier` giả; thử supplier trả 10 để xác minh validation.
5. Hai `SplittableRandom(2026L)` với cùng thứ tự gọi cho 500 kết quả bằng nhau.
6. Hai `Random(7)` với cùng thứ tự gọi cho 500 kết quả bằng nhau.
7. Pool có 4 worker; mỗi worker tự gọi `ThreadLocalRandom.current()` 20.000 lần và kiểm tra range; không share RNG giữa threads.
8. Shutdown/await pool và in status ổn định.

Không có assertion về **giá trị ngẫu nhiên cụ thể**, số lần trùng hay histogram. Vì thế output có thể kiểm chứng chính xác mà không bị lệ thuộc seed nội bộ.

### 10.1. Mã nguồn đầy đủ

```java
import java.util.Objects;
import java.util.Random;
import java.util.SplittableRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.function.IntSupplier;
import java.util.random.RandomGenerator;

public final class ThreadLocalRandomTestingDemo {
    private static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
    }

    static final class BucketService {
        private final IntSupplier draw;

        BucketService(IntSupplier draw) {
            this.draw = Objects.requireNonNull(draw);
        }

        String bucket() {
            int value = draw.getAsInt();
            if (value < 0 || value >= 10) {
                throw new IllegalArgumentException("out of [0, 10)");
            }
            return value < 3 ? "EARLY" : "NORMAL";
        }
    }

    static final class Picker {
        private final RandomGenerator random;

        Picker(RandomGenerator random) {
            this.random = Objects.requireNonNull(random);
        }

        int choose() {
            return random.nextInt(100, 200);
        }
    }

    public static void main(String[] args) throws Exception {
        boolean seedRejected = false;
        try {
            ThreadLocalRandom.current().setSeed(42);
        } catch (UnsupportedOperationException expected) {
            seedRejected = true;
        }
        check(seedRejected, "ThreadLocalRandom seed should be unavailable");
        System.out.println("ThreadLocalRandom.setSeed rejected = true");

        for (int i = 0; i < 50_000; i++) {
            int value = ThreadLocalRandom.current().nextInt(-5, 8);
            check(value >= -5 && value < 8, "bound invariant");
        }
        System.out.println("range invariant without fixed seed = PASS");

        boolean invalidBoundRejected = false;
        try {
            ThreadLocalRandom.current().nextInt(4, 4);
        } catch (IllegalArgumentException expected) {
            invalidBoundRejected = true;
        }
        check(invalidBoundRejected, "equal bounds should fail");
        System.out.println("invalid bounds rejected = true");

        BucketService fixedLow = new BucketService(() -> 2);
        BucketService fixedHigh = new BucketService(() -> 9);
        check("EARLY".equals(fixedLow.bucket()), "low branch");
        check("NORMAL".equals(fixedHigh.bucket()), "high branch");
        boolean rejectedStub = false;
        try {
            new BucketService(() -> 10).bucket();
        } catch (IllegalArgumentException expected) {
            rejectedStub = true;
        }
        check(rejectedStub, "invalid stub should fail");
        System.out.println("stubbed branches and validation = PASS");

        Picker a = new Picker(new SplittableRandom(2026L));
        Picker b = new Picker(new SplittableRandom(2026L));
        for (int i = 0; i < 500; i++) {
            check(a.choose() == b.choose(), "same seed, same call order");
        }
        Random specA = new Random(7);
        Random specB = new Random(7);
        for (int i = 0; i < 500; i++) {
            check(specA.nextInt(1_000) == specB.nextInt(1_000),
                    "seeded Random sequence");
        }
        System.out.println("seeded alternatives repeat = PASS");

        ExecutorService workers = Executors.newFixedThreadPool(4);
        try {
            @SuppressWarnings("unchecked")
            Future<Boolean>[] results = (Future<Boolean>[]) new Future<?>[4];
            for (int i = 0; i < results.length; i++) {
                results[i] = workers.submit(() -> {
                    for (int step = 0; step < 20_000; step++) {
                        int value = ThreadLocalRandom.current().nextInt(0, 100);
                        if (value < 0 || value >= 100) return false;
                    }
                    return true;
                });
            }
            for (Future<Boolean> result : results) {
                check(result.get(5, TimeUnit.SECONDS),
                        "concurrent range failed");
            }
        } finally {
            workers.shutdownNow();
            check(workers.awaitTermination(5, TimeUnit.SECONDS),
                    "pool termination failed");
        }
        System.out.println("concurrent worker ranges = PASS");
        System.out.println("checks = PASS");
    }
}
```

### 10.2. Biên dịch và chạy bằng Java 17

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 ThreadLocalRandomTestingDemo.java
java ThreadLocalRandomTestingDemo
```

Đã biên dịch và chạy thực tế với JDK 17, **stdout chính xác bảy dòng**:

```text
ThreadLocalRandom.setSeed rejected = true
range invariant without fixed seed = PASS
invalid bounds rejected = true
stubbed branches and validation = PASS
seeded alternatives repeat = PASS
concurrent worker ranges = PASS
checks = PASS
```

Các dòng in thể hiện điều kiện đã kiểm tra. Chương trình cố ý **không in giá trị random** vì dãy đó thay đổi theo lượt chạy và không phải expected output đáng tin.

### 10.3. Vì sao không có expected sequence của ThreadLocalRandom?

Vì API **không cung cấp cách đặt seed công khai** và mỗi worker có state nội bộ. Dù tại một lần chạy bạn quan sát được `21,14,37,...`, nó không trở thành cam kết cho các lần chạy sau. Bài test phải bám vào contract như range, exception và logic đã được stub.

### 10.4. Vì sao test two seeded generators bằng cách đối chiếu nhau?

Hai generator cùng loại, cùng seed và cùng số lượng/thứ tự lời gọi cho chuỗi tương đương trong môi trường kiểm thử. Đây là cách xác minh **tính tái hiện của dependency được chọn**, không phải kiểm tra giá trị ThreadLocalRandom.

Nếu muốn golden sequence tồn tại nhiều năm, chọn thuật toán có bảo đảm rõ và ghi version cụ thể; `Random` truyền thống có contract thuật toán xác định như đã nêu.

### 10.5. Vì sao không kiểm tra giá trị random luôn khác nhau giữa threads?

Hai threads có thể phát sinh cùng một số hoàn toàn hợp lệ. Test concurrency nên xác minh range và không có exception/data race từ **cách dùng API đúng**, không assert không trùng.

### 10.6. Vì sao dùng Future.get?

`Future.get(5,TimeUnit.SECONDS)` thu kết quả và propagate lỗi từ worker, giúp main phát hiện một assertion thất bại. Test không dựa vào việc chỉ submit task rồi in "PASS" khi worker có thể chưa hoàn tất.

Nếu máy CI bị quá tải, timeout có thể fail dù logic đúng; điều đó cần điều tra tài nguyên, không được che bằng cách nuốt exception.

## 11. Thiết kế test cho chương trình thực tế

### 11.1. Ví dụ A/B assignment

Giả sử một user được phân vào bucket A với xác suất khoảng 10%:

```java
String assign(IntSupplier draw) {
    int n = draw.getAsInt();
    if (n < 0 || n >= 100) {
        throw new IllegalArgumentException("invalid bucket");
    }
    return n < 10 ? "A" : "B";
}
```

Đây là method minh họa. Unit test nên inject:

- `() -> 0`: A, biên thấp.
- `() -> 9`: A, biên cuối.
- `() -> 10`: B, biên đầu.
- `() -> 99`: B, biên trên hợp lệ.
- `() -> -1` và `() -> 100`: lỗi validation.

**Không cần** lặp 1.000 lần với random thật để mong chạm đúng `9` và `10`.

Nếu bucket assignment cần **ổn định cho cùng user** qua nhiều request, `ThreadLocalRandom` có thể là **sai mô hình nghiệp vụ**: hãy cân nhắc stable hashing với salt/version hoặc cơ chế phân nhóm ổn định có lưu trạng thái, không dùng một RNG tạo bucket mới mỗi lần.

### 11.2. Jitter và backoff

Một bộ tính jitter có thể:

```java
long addJitter(long baseMillis, java.util.function.LongSupplier jitter) {
    long delta = jitter.getAsLong();
    if (delta < 0 || delta > 100) {
        throw new IllegalArgumentException("invalid jitter");
    }
    return Math.addExact(baseMillis, delta);
}
```

Đây là method minh họa, dùng `Math.addExact` để không âm thầm overflow. Test deterministic khi `delta=0`, `delta=100`, `delta=101` hoặc `baseMillis` gần `Long.MAX_VALUE`. Production supplier có thể gọi `ThreadLocalRandom.current().nextLong(0,101)` cho khoảng **[0,101)**; cần hiểu biên trên.

Nếu muốn jitter trong [0,100] ms và không bảo đảm SLA cứng, việc thêm 100 ms là có thể. Với retry/backoff nghiêm ngặt, tính toán cần deadline tổng, giới hạn số lần thử và chính sách cancel — không chỉ một số random.

### 11.3. Random choice trong business rule

Khi logic phụ thuộc nhiều lần lấy số, hãy biến các lần lấy thành một abstraction rõ, có thể test bằng sequence cố định. Ví dụ một `IntSupplier` giả trả lần lượt 2,9,3 cho ba quyết định; unit test kiểm tra đúng thứ tự gọi và kết quả.

Không nên gọi `ThreadLocalRandom.current()` sâu trong nhiều private methods nếu business test cần điều khiển cả luồng: injection ở constructor hoặc method parameter giúp test không cần dùng reflection.

### 11.4. Test tính đúng đắn với nhiều thread

Trong thread pool, mỗi worker gọi `current()` ngay tại điểm cần. Bài test nên thu kết quả qua `Future`/structured coordination, có timeout phù hợp, shutdown pool, và kiểm tra tất cả giá trị trả trong domain.

Nếu mỗi task còn sửa shared map/list, cần kiểm tra thread-safety của **map/list** riêng. `ThreadLocalRandom` không tự làm an toàn các object khác.

## 12. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `ThreadLocalRandom.current().setSeed(123)` | Ném `UnsupportedOperationException` | Dùng seedable generator cho test |
| Assert một số ngẫu nhiên cụ thể | Seed nội bộ không điều khiển được | Kiểm tra invariant/tiêm fake |
| Capture `ThreadLocalRandom` ở main rồi chia sẻ worker | Instance chỉ nên dùng bởi current thread | Gọi `current()` trong từng worker |
| Tưởng thread-local tương đương request-local | Pool thread được tái sử dụng | Không dựa vào mapping request/seed |
| Assert hai lần lấy phải khác | Sự trùng ngẫu nhiên hợp lệ | Test range và mapping |
| Assert các worker phải sinh kết quả duy nhất | Không có uniqueness guarantee | IDs cần uniqueness kiểm soát |
| Đặt phân phối đúng 50/50 cho 20 mẫu | Random sample có dao động | Statistical test có thiết kế riêng |
| Gọi random nhiều lần trong một assertion | Tiêu thụ state khác nhau | Lưu một output rồi kiểm tra |
| Dùng `Math.abs(nextInt())%N` | Có thể overflow với MIN_VALUE và gây bias | `nextInt(bound)` |
| Dùng modulo để chia bucket | Có thể gây bias | Dùng bounded API |
| Dùng random thật để test nhánh hiếm | Test có thể không chạm nhánh | Inject fake giá trị biên |
| Thay production thành `Random(42)` mọi lúc | Output predictability và contention thay đổi | Tách dependency test/production |
| Tin mọi PRNG seed giống nhau | Thuật toán khác cho output khác | Ghi thuật toán và seed |
| Dùng reflection đọc state TLR | Không phải API hỗ trợ | Không can thiệp internal implementation |
| Bật property secureRandomSeed để seed có thể điều khiển | Property khác API setSeed | Dùng seedable alternative |
| Dùng TLR cho OTP/secret | Không cryptographically secure | `SecureRandom` |
| Dùng histogram nhỏ làm gate CI | False positives/flakiness | Tách statistical tests |
| Test throughput bằng random sampling mà không kiểm soát seed | Nhiễu benchmark | Cố định workload/test data |
| Test worker bằng việc chỉ submit rồi PASS | Chưa biết task hoàn tất/lỗi | `Future.get` và timeout |
| Dùng `sleep` để đoán thứ tự worker | Scheduler không xác định | Latch/barrier khi cần |
| Coi unit test seeded là kiểm thử TLR thực | Đó là kiểm thử business logic với dependency khác | Có thêm invariant integration tests với TLR |
| Dùng RNG để ổn định bucket theo user qua request | Kết quả thay đổi mỗi lần | Stable hash/versioned mapping |
| Hardcode “Java 7 mới nhất” | Nhiều API hiện đại thêm từ JDK khác | Ghi rõ `RandomGenerator` có từ Java 17 |

## 13. Bài tập tự luyện có đáp án

### Bài 1 — setSeed

`ThreadLocalRandom.current().setSeed(7)` có làm dãy số lặp lại được không?

**Đáp án:** Không. `setSeed` ném `UnsupportedOperationException` theo hợp đồng.

### Bài 2 — Kiểm tra range

Đâu là assert đáng tin cho `nextInt(10,20)`?

**Đáp án:** `value >= 10 && value < 20`. Không assert `value == 15`.

### Bài 3 — Upper bound

`nextInt(0,10)` có thể trả 10 không?

**Đáp án:** Không. Upper bound exclusive; các giá trị hợp lệ là 0..9.

### Bài 4 — Invalid range

`nextInt(3,3)` có xảy ra lỗi gì?

**Đáp án:** `IllegalArgumentException`; không có số nào thuộc khoảng rỗng.

### Bài 5 — Nhánh hiếm

Ứng dụng có nhánh chỉ khi random=0 trong [0,1000). Unit test nên làm gì?

**Đáp án:** Inject supplier trả 0 cho nhánh đó, thêm test các giá trị sát biên và adapter production.

### Bài 6 — Lặp lại

`new Random(42)` hai lần với cùng thứ tự gọi có thể cho cùng chuỗi không?

**Đáp án:** Có. `Random` định nghĩa thuật toán theo chuẩn để các instance với cùng seed và call pattern sinh cùng output.

### Bài 7 — SplittableRandom

Hai `SplittableRandom(42)` có mục đích gì trong unit test?

**Đáp án:** Cho nguồn số có thể seed, tái hiện sequence trong điều kiện thuật toán và thứ tự lời gọi tương đương; không phải setSeed cho TLR.

### Bài 8 — Thread pool

Có nên lưu `static final ThreadLocalRandom RANDOM = ThreadLocalRandom.current()` ở main rồi dùng mọi worker không?

**Đáp án:** Không. Dùng `current()` bên trong mỗi thread để tuân thủ hợp đồng.

### Bài 9 — Tính bảo mật

Có dùng `ThreadLocalRandom` sinh reset token được không?

**Đáp án:** Không. Dùng `SecureRandom` và protocol mã hóa/xác thực phù hợp.

### Bài 10 — Test không trùng

Nếu hai giá trị `nextInt(100)` liên tiếp bằng nhau, có phải bug không?

**Đáp án:** Không. Trùng là kết quả hợp lệ trong random sampling.

### Bài 11 — Statistical test

Tại sao không assert mỗi bucket đúng 100 lần trên 1000 mẫu?

**Đáp án:** Sai về phân phối hữu hạn; tần suất dao động. Cần kiểm định thống kê có mức ý nghĩa nếu thật sự cần kiểm tra bias.

### Bài 12 — Supplier giả

`new BucketService(() -> 9).bucket()` nên trả gì?

**Đáp án:** `NORMAL`, deterministic, không cần random thật.

### Bài 13 — Supplier lỗi

`new BucketService(() -> 10).bucket()` có nên được chấp nhận không?

**Đáp án:** Không. 10 ngoài [0,10), bị `IllegalArgumentException`.

### Bài 14 — Cùng seed, khác thuật toán

Hai generator khác thuật toán nhưng cùng seed 2026 có bắt buộc cùng output không?

**Đáp án:** Không. Seed chỉ có ý nghĩa trong một thuật toán/implementation cụ thể.

### Bài 15 — Test concurrency

Trong bốn worker độc lập, nên assert gì với `nextInt(0,100)`?

**Đáp án:** Mỗi giá trị thuộc [0,100), các futures hoàn tất không lỗi. Không assert output giữa workers khác nhau.

### Bài 16 — Business mapping

Bucket A được chọn nếu n < 10 trên range [0,100). Nên test những biên nào?

**Đáp án:** 0,9 thuộc A; 10,99 thuộc B; -1 và 100 phải bị validation từ chối.

### Bài 17 — Stable allocation

Muốn user ID 123 luôn thuộc cùng nhóm qua mọi request. `ThreadLocalRandom` có phù hợp không?

**Đáp án:** Không phải lựa chọn tự nhiên. Dùng stable hash/versioned assignment hoặc lưu kết quả phân nhóm.

### Bài 18 — Reproducibility

Để tái hiện lỗi sau một tháng, chỉ log “seed=17” đủ chưa?

**Đáp án:** Chưa chắc. Cần thuật toán, phiên bản hoặc hợp đồng thuật toán, thứ tự lời gọi và input/config liên quan.

### Bài 19 — Math.abs và modulo

`Math.abs(random.nextInt()) % 10` có thay thế an toàn `nextInt(10)` không?

**Đáp án:** Không. `Math.abs(Integer.MIN_VALUE)` vẫn âm và modulo có thể gây bias. Dùng bounded API.

### Bài 20 — Property-based test

Một property test thực tế không seed trên TLR nên tập trung gì?

**Đáp án:** Range, invalid input, transformation invariants và những thuộc tính đúng cho **mọi output hợp lệ**, không ép random trả số cụ thể.

## 14. Checklist cho dự án

- [ ] Xác định rõ code cần **random production** hay **replay deterministic** trong test.
- [ ] Không gọi `ThreadLocalRandom.setSeed`; API không hỗ trợ.
- [ ] Không lấy/giữ một instance TLR rồi dùng cross-thread.
- [ ] Gọi `ThreadLocalRandom.current()` tại worker đang cần.
- [ ] Test range với biên trên exclusive và invalid args.
- [ ] Không assert các output TLR phải trùng golden sequence.
- [ ] Không assert uniqueness hoặc histogram chuẩn xác từ mẫu nhỏ.
- [ ] Tách business logic khỏi RNG bằng `IntSupplier`, `RandomGenerator` hoặc abstraction phù hợp.
- [ ] Unit test các nhánh bằng fake supplier giá trị biên.
- [ ] Test seeded generator với cùng thuật toán, seed và call pattern.
- [ ] Nếu cần replay lâu dài, lưu algorithm/version/config và inputs.
- [ ] Không biến tất cả code production thành seeded RNG vì test.
- [ ] Không dùng TLR cho secret/token mật mã.
- [ ] Mỗi concurrency worker tự lấy TLR, thu mọi Future để phát hiện lỗi.
- [ ] Có timeout/shutdown executor trong tests.
- [ ] Tách statistical test khỏi unit CI deterministic.
- [ ] Đo false positive/flaky probability nếu dùng test ngẫu nhiên thực.
- [ ] Không dùng `Math.abs(nextInt())%N` thay bounded API.
- [ ] Dùng cơ chế cấp unique ID có kiểm soát nếu không được phép trùng.
- [ ] Chỉ dùng API Java còn phù hợp hiện tại; biết `RandomGenerator` từ Java 17.

## 15. Tài liệu Java chính thức

- [Java SE 17 — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): `current`, giới hạn sử dụng theo thread, `setSeed` luôn từ chối, bounds và lưu ý không phù hợp mật mã.
- [Java SE 17 — Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): seeded PRNG có thuật toán và hợp đồng tái hiện xác định.
- [Java SE 17 — SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): generator có seed, phù hợp nhiều kiểu chương trình/test.
- [Java SE 17 — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): abstraction hiện đại cho nhiều generator và bounded methods.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): nguồn RNG thích hợp cho trường hợp nhạy cảm về bảo mật.

## 16. Tổng kết

Không thể điều khiển seed của `ThreadLocalRandom` bằng API công khai: `setSeed(long)` **luôn ném UnsupportedOperationException**. Để kiểm thử đáng tin, hãy **kiểm tra invariants và preconditions** của các phương thức random, **tiêm nguồn số có thể điều khiển** vào business logic và chỉ dùng PRNG **có seed** khi test thực sự yêu cầu replay một dãy.

Những thay đổi ở thread scheduling, thứ tự lời gọi, số worker, JDK implementation và điều kiện chạy có thể khiến một số ngẫu nhiên quan sát được khác đi. Unit test tốt **không phụ thuộc con số đó**, nhưng vẫn kiểm thử được đầy đủ mọi nhánh quan trọng và điều kiện biên.

Với Java hiện đại, `IntSupplier`, `RandomGenerator` và các seedable generators là công cụ hữu ích để đạt khả năng test mà không phải xâm nhập private state của JVM. Còn `ThreadLocalRandom.current()` giữ đúng vai trò **nguồn random không bảo mật, ít tranh chấp cho mỗi thread** trong production.