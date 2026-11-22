# Collections.shuffle với RandomGenerator

Java 21 bổ sung overload `Collections.shuffle(List<?>, RandomGenerator)` để xáo trộn một `List` bằng bất kỳ nguồn ngẫu nhiên nào triển khai `java.util.random.RandomGenerator`. API này giúp chọn thuật toán sinh số ngẫu nhiên, đặt seed để tái lập kết quả hoặc dùng `SecureRandom` khi cần tính khó dự đoán.

`Collections.shuffle` thay đổi thứ tự phần tử ngay trên list được truyền vào. Phương thức dùng thuật toán Fisher–Yates, chạy trong thời gian tuyến tính và tạo các hoán vị có xác suất bằng nhau nếu nguồn ngẫu nhiên cung cấp các giá trị công bằng.

## 1. Cú pháp và overload trong Java 21

Java 21 có ba overload chính:

```java
Collections.shuffle(list);
Collections.shuffle(list, random);
Collections.shuffle(list, randomGenerator);
```

| Overload | Nguồn ngẫu nhiên | Ghi chú |
|---|---|---|
| `shuffle(List<?> list)` | Nguồn ngẫu nhiên mặc định | Thuận tiện khi không cần kiểm soát generator hoặc seed |
| `shuffle(List<?> list, Random rnd)` | Một `Random` do caller cung cấp | Vẫn được hỗ trợ để tương thích; overload `RandomGenerator` linh hoạt hơn |
| `shuffle(List<?> list, RandomGenerator rnd)` | Bất kỳ implementation nào của `RandomGenerator` | Có từ Java 21; nên dùng khi thiết kế API mới cần nhận nguồn ngẫu nhiên tổng quát |

Ví dụ đơn giản:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

static void shuffleCards() {
    List<String> cards = new ArrayList<>(
            List.of("A", "K", "Q", "J", "10"));

    RandomGenerator random =
            RandomGeneratorFactory.of("L64X128MixRandom").create();

    Collections.shuffle(cards, random);
    System.out.println(cards);
}
```

Overload `RandomGenerator` nhận interface thay vì yêu cầu một lớp cụ thể kế thừa `Random`. Nhờ vậy, code có thể dùng các thuật toán hiện đại trong package `java.util.random`, `ThreadLocalRandom`, `SplittableRandom` hoặc `SecureRandom` mà không cần đổi cách gọi `Collections.shuffle`.

## 2. Shuffle thay đổi list tại chỗ

`Collections.shuffle` không tạo và trả về một list mới. Nó hoán đổi vị trí các phần tử trong chính list đầu vào; kiểu trả về là `void`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.random.RandomGenerator;

static List<String> shuffledCopy(
        List<String> source, RandomGenerator random) {
    List<String> result = new ArrayList<>(source);
    Collections.shuffle(result, random);
    return result;
}
```

Ví dụ tạo bản sao trước khi shuffle phù hợp khi cần giữ nguyên thứ tự ban đầu. `new ArrayList<>(source)` tạo một list mutable mới; `shuffle` chỉ thay đổi thứ tự trong bản sao đó.

Các phần tử không bị thêm hoặc xóa. Nếu list có phần tử trùng nhau, mọi vị trí vẫn được xáo trộn; hai phần tử có cùng giá trị có thể khiến một số hoán vị vị trí nhìn giống nhau khi quan sát giá trị.

## 3. Thuật toán Fisher–Yates

Implementation của `Collections.shuffle` duyệt list từ cuối về đầu. Ở mỗi vị trí `i`, thuật toán chọn ngẫu nhiên một chỉ số `j` trong đoạn từ `0` đến `i`, rồi đổi chỗ hai phần tử.

```text
Ban đầu:  [A, B, C, D, E]

i = 4: chọn j trong [0, 4], đổi phần tử ở vị trí 4
i = 3: chọn j trong [0, 3], đổi phần tử ở vị trí 3
i = 2: chọn j trong [0, 2], đổi phần tử ở vị trí 2
i = 1: chọn j trong [0, 1], đổi phần tử ở vị trí 1

Kết quả: một hoán vị của list ban đầu
```

Với nguồn ngẫu nhiên công bằng, mỗi vị trí được chọn đồng đều trong phạm vi còn lại. Vì vậy, mỗi hoán vị có xác suất như nhau. Thuật toán thực hiện số thao tác tỷ lệ tuyến tính theo số phần tử, tức O(n).

Không nên tự viết cách shuffle bằng cách sắp xếp list theo một random key hoặc gọi `nextInt()` không giới hạn rồi lấy modulo. Những cách đó có thể tạo phân phối lệch hoặc lỗi modulo bias. Dùng API chuẩn để tránh các sai sót này.

## 4. Chọn RandomGenerator và thuật toán cụ thể

`RandomGenerator` là interface chung cho nguồn số ngẫu nhiên hoặc giả ngẫu nhiên. Java cung cấp `RandomGeneratorFactory` để tìm và tạo instance theo tên thuật toán.

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

static RandomGenerator createGenerator() {
    return RandomGeneratorFactory
            .of("L64X128MixRandom")
            .create();
}
```

Có thể lấy generator mặc định:

```java
RandomGenerator random = RandomGenerator.getDefault();
```

`getDefault()` chọn một implementation đáp ứng yêu cầu tối thiểu của API. Thuật toán mặc định có thể thay đổi giữa các bản JDK; không nên dựa vào nó nếu ứng dụng cần tái lập chính xác chuỗi kết quả qua các lần chạy hoặc nâng cấp runtime.

Khi cần chọn thuật toán rõ ràng, dùng `RandomGeneratorFactory.of("algorithm-name")`. Nếu tên không được runtime hỗ trợ, phương thức ném `IllegalArgumentException`. Hãy chọn thuật toán có trong runtime mục tiêu và kiểm tra tài liệu của thuật toán đó.

## 5. Seed để tái lập thứ tự shuffle

Để tái lập kết quả trong kiểm thử hoặc mô phỏng, tạo generator từ thuật toán cụ thể và seed cố định:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

static List<Integer> deterministicShuffle() {
    List<Integer> values = new ArrayList<>(
            List.of(1, 2, 3, 4, 5, 6));

    RandomGenerator random = RandomGeneratorFactory
            .of("L64X128MixRandom")
            .create(2026L);

    Collections.shuffle(values, random);
    return values;
}
```

Với cùng thuật toán, seed, dữ liệu đầu vào và thứ tự lời gọi generator, kết quả có thể được tái lập trong cùng implementation. Không dùng `RandomGenerator.getDefault()` nếu cần kiểm soát thuật toán qua các lần chạy.

Khi cần tái lập tuyệt đối giữa các môi trường hoặc phiên bản JDK khác nhau, hãy xác minh cam kết tương thích của thuật toán và runtime cụ thể; chỉ lưu seed mà không lưu tên thuật toán và môi trường là chưa đủ.

## 6. Dùng Random có sẵn hoặc ThreadLocalRandom

`Random` triển khai `RandomGenerator`, vì vậy có thể truyền một instance `Random` vào overload mới:

```java
import java.util.Random;

Random random = new Random(42L);
Collections.shuffle(items, random);
```

Overload `shuffle(List<?>, Random)` vẫn tồn tại để tương thích ngược. Khi viết API mới nhận một nguồn ngẫu nhiên, dùng kiểu `RandomGenerator` để không giới hạn caller vào các generator kế thừa lớp `Random`.

`ThreadLocalRandom.current()` cũng triển khai `RandomGenerator` và phù hợp khi mỗi thread tự shuffle list riêng:

```java
import java.util.concurrent.ThreadLocalRandom;

Collections.shuffle(items, ThreadLocalRandom.current());
```

`ThreadLocalRandom` cung cấp nguồn ngẫu nhiên riêng theo thread, hữu ích trong ứng dụng đa luồng. Tuy nhiên, nếu nhiều thread cùng sửa một list, bản thân list vẫn có thể bị race condition; nguồn random theo thread không làm list trở nên thread-safe.

## 7. Generator cho xử lý song song

Các implementation của `RandomGenerator` không nhất thiết thread-safe. Không nên mặc định chia sẻ một generator bất kỳ giữa nhiều thread đang shuffle đồng thời.

Các lựa chọn thường dùng:

- Dùng `ThreadLocalRandom.current()` trong từng thread khi mỗi thread thao tác trên list riêng.
- Dùng generator hỗ trợ split/jump để tạo các luồng ngẫu nhiên riêng cho từng tác vụ song song.
- Dùng `SecureRandom` nếu cần nguồn ngẫu nhiên khó dự đoán cho mục đích bảo mật; cân nhắc chi phí và cách chia sẻ instance theo tài liệu của implementation.

Ví dụ, nếu các tác vụ xử lý độc lập, tạo generator riêng cho từng tác vụ rồi shuffle list riêng của nó. Không chỉ tránh chia sẻ generator không thread-safe, cách này còn giúp mỗi tác vụ có trạng thái random dễ quản lý hơn.

## 8. Khi cần tính khó dự đoán: SecureRandom

Các generator giả ngẫu nhiên thông thường phục vụ mô phỏng, game, kiểm thử hoặc xáo trộn dữ liệu không nhạy cảm. Chúng không mặc nhiên phù hợp để tạo thứ tự mà đối thủ không thể dự đoán.

`SecureRandom` triển khai `RandomGenerator`, nên có thể truyền trực tiếp vào `Collections.shuffle`:

```java
import java.security.SecureRandom;

SecureRandom secureRandom = new SecureRandom();
Collections.shuffle(deck, secureRandom);
```

Đối với trò chơi có tiền cược, bốc thăm có yêu cầu bảo mật hoặc quy trình cần chống dự đoán, hãy chọn `SecureRandom` và đánh giá toàn bộ thiết kế bảo mật, bao gồm cách khởi tạo, triển khai, kiểm toán và xử lý kết quả. Chỉ đổi sang `SecureRandom` không tự bảo đảm toàn bộ quy trình nghiệp vụ công bằng hoặc chống gian lận.

Không dùng `RandomGenerator.getDefault()` hoặc một seed cố định để tạo token, mật khẩu, nonce hay thứ tự cần bí mật. Với các dữ liệu đó, dùng API mật mã chuyên dụng.

## 9. Yêu cầu đối với list có thể thay đổi

`Collections.shuffle` cần thay đổi phần tử tại các vị trí trong list. Nếu list hoặc `ListIterator` của nó không hỗ trợ thao tác `set`, phương thức ném `UnsupportedOperationException`.

| Loại list | Có thể shuffle? | Giải thích |
|---|---|---|
| `ArrayList` | Có | Hỗ trợ thay thế phần tử theo vị trí |
| `LinkedList` | Có | Hỗ trợ thay thế qua list iterator; implementation tránh truy cập tuần tự gây O(n²) bằng cách dùng mảng trung gian khi list lớn |
| `Arrays.asList(...)` | Có | Kích thước cố định nhưng hỗ trợ `set`, nên có thể hoán đổi phần tử |
| `List.of(...)` | Không | List bất biến, không hỗ trợ thay thế phần tử |
| Unmodifiable list wrapper | Không | Không cho phép sửa đổi qua wrapper |

Ví dụ với list bất biến, hãy tạo bản sao mutable trước:

```java
List<String> fixed = List.of("red", "green", "blue");
List<String> mutable = new ArrayList<>(fixed);
Collections.shuffle(mutable, random);
```

List rỗng hoặc list chỉ có một phần tử không thay đổi thứ tự sau shuffle. Nếu list có nhiều phần tử nhưng không hỗ trợ `set`, phương thức có thể ném `UnsupportedOperationException`.

## 10. Độ phức tạp và lưu ý hiệu năng

`Collections.shuffle` chạy trong O(n). Với list hỗ trợ `RandomAccess`, implementation có thể hoán đổi trực tiếp theo chỉ số. Với list tuần tự lớn không hỗ trợ `RandomAccess`, implementation dùng mảng trung gian để tránh việc truy cập chỉ số lặp lại gây hiệu năng bậc hai.

Chi phí thực tế còn phụ thuộc generator, kích thước list và loại list. Nếu shuffle list rất lớn thường xuyên, hãy đo trên dữ liệu thực tế. Tránh tạo generator mới cho mỗi phần tử; tạo một generator phù hợp cho vòng đời tác vụ hoặc thành phần cần dùng.

## 11. Những điều Collections.shuffle không làm

- Không tạo list mới; thứ tự đầu vào bị thay đổi.
- Không loại bỏ phần tử trùng lặp và không thay đổi số lượng phần tử.
- Không tạo shuffle có trọng số; mọi vị trí được xử lý theo thuật toán hoán vị đồng đều.
- Không bảo đảm bí mật nếu nguồn random là PRNG thông thường.
- Không làm list thread-safe khi nhiều thread cùng sửa list.
- Không bảo đảm hai lần gọi cho ra thứ tự khác nhau; kết quả phụ thuộc trạng thái generator và có thể trùng nhau.

Nếu cần shuffle có trọng số, chọn mẫu không hoàn lại, hoặc bốc thăm theo quy tắc nghiệp vụ đặc biệt, cần thuật toán phù hợp với yêu cầu đó thay vì giả định `Collections.shuffle` hỗ trợ trực tiếp.

## 12. Ví dụ thực tế: xáo trộn danh sách câu hỏi kiểm thử

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

record Question(String id, String text) {}

static List<Question> randomizedQuestions(List<Question> source, long seed) {
    List<Question> questions = new ArrayList<>(source);
    RandomGenerator random = RandomGeneratorFactory
            .of("L64X128MixRandom")
            .create(seed);

    Collections.shuffle(questions, random);
    return questions;
}
```

Caller truyền seed để có thể lặp lại một lượt kiểm thử. Mỗi lần gọi tạo một generator mới với cùng thuật toán và seed, rồi shuffle một bản sao để giữ nguyên danh sách câu hỏi gốc.

Trong hệ thống thi hoặc đánh giá thực tế, cần xác định liệu thứ tự có phải bí mật hay không. Nếu cần chống dự đoán, dùng nguồn ngẫu nhiên bảo mật và quản lý seed theo chính sách bảo mật thay vì ghi seed cố định vào log.

## 13. API Java 21 cần nhớ

| API | Vai trò |
|---|---|
| `Collections.shuffle(List<?>)` | Shuffle bằng nguồn random mặc định |
| `Collections.shuffle(List<?>, RandomGenerator)` | Shuffle bằng generator do caller cung cấp; có từ Java 21 |
| `RandomGenerator` | Interface chung cho nguồn số ngẫu nhiên |
| `RandomGenerator.getDefault()` | Lấy generator mặc định của runtime |
| `RandomGeneratorFactory.of(String)` | Chọn factory theo tên thuật toán |
| `RandomGeneratorFactory.create(long)` | Tạo generator với seed chỉ định |
| `ThreadLocalRandom.current()` | Lấy generator gắn với thread hiện tại |
| `SecureRandom` | Nguồn ngẫu nhiên phù hợp cho mục đích bảo mật |

## 14. Biên dịch với Java 21

Overload `Collections.shuffle(List<?>, RandomGenerator)` có từ Java 21. Có thể biên dịch mã nguồn bằng release 21 mà không cần bật Preview:

```bash
javac --release 21 -d out src/ShuffleDemo.java
java -cp out ShuffleDemo
```

Đặt compiler release hoặc toolchain về Java 21 để kiểm tra đúng API mục tiêu. Nếu dự án chạy trên JDK thấp hơn 21, overload nhận `RandomGenerator` không có sẵn; cần nâng runtime/compiler hoặc dùng overload tương thích với phiên bản mục tiêu.

## 15. Tài liệu tham khảo

- [Java SE 21 API — Collections.shuffle(List, RandomGenerator)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#shuffle(java.util.List,java.util.random.RandomGenerator))
- [Java SE 21 API — RandomGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/random/RandomGenerator.html)
- [Java SE 21 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/random/RandomGeneratorFactory.html)
- [Java SE 21 API — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html)
- [Java SE 21 API — SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html)
