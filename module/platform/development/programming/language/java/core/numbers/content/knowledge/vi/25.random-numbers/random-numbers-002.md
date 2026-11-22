# Random và chuỗi giá trị theo seed trong Java

## 1. Seed là gì và tại sao cùng seed có thể phát lại cùng chuỗi?

`java.util.Random` là bộ sinh **số giả ngẫu nhiên** (pseudorandom number generator, PRNG). Thay vì tạo ra sự ngẫu nhiên tuyệt đối, đối tượng giữ một **trạng thái nội bộ**; mỗi lần chương trình yêu cầu số tiếp theo, thuật toán cập nhật trạng thái và tính ra kết quả. Giá trị khởi tạo trạng thái được gọi là **seed** (hạt giống).

~~~java
Random random = new Random(42L);
int value = random.nextInt(100);
~~~

Trong ví dụ, `42L` là seed; `nextInt(100)` sinh một số nguyên từ **0 (bao gồm) đến 100 (không bao gồm)**, tức từ 0 đến 99.

Thuộc tính quan trọng:

> Với **cùng triển khai thuật toán, cùng seed, cùng các lời gọi theo cùng thứ tự và cùng tham số**, ta nhận được cùng một chuỗi kết quả.

Đây là nền tảng để phát lại mô phỏng, tái hiện lỗi, tạo dữ liệu kiểm thử và so sánh hai lần chạy thí nghiệm. Một seed cố định giúp **tái lập** (reproducibility); nó không làm giá trị sinh ra trở thành bí mật hoặc an toàn về mật mã.

Cần phân biệt:

- **Seed** là dữ liệu dùng để thiết lập trạng thái ban đầu.
- **Trạng thái hiện tại** thay đổi khi tiêu thụ số ngẫu nhiên. Sau khi gọi phương thức sinh số, đối tượng thường không còn ở trạng thái ban đầu nữa.
- **Chuỗi giá trị** được xác định bởi seed **và** trình tự sử dụng bộ sinh, không chỉ bởi seed đứng riêng.

## 2. Hai Random cùng seed: giống chuỗi, không chia sẻ trạng thái

Xét hai đối tượng độc lập:

~~~java
Random first = new Random(42L);
Random second = new Random(42L);
~~~

Nếu cả hai đều lần lượt gọi `nextInt(100)` năm lần, kết quả của từng vị trí trùng nhau:

| Lần gọi | `first.nextInt(100)` | `second.nextInt(100)` |
| ---: | ---: | ---: |
| 1 | 30 | 30 |
| 2 | 63 | 63 |
| 3 | 48 | 48 |
| 4 | 84 | 84 |
| 5 | 70 | 70 |

Hai đối tượng **không phải cùng một đối tượng**: tăng trạng thái của `first` không tự làm `second` tăng theo. Chúng chỉ tạo cùng chuỗi khi được khởi tạo từ cùng seed và tiêu thụ lời gọi tương ứng.

Ngược lại, nếu một đối tượng đã gọi thêm một lần, vị trí đọc kế tiếp của hai đối tượng có thể khác:

~~~text
Random A (seed 42): nextInt(100) -> 30, rồi -> 63
Random B (seed 42): chưa gọi   -> 30 ở lời gọi đầu tiên
~~~

Vì thế, một câu hỏi chính xác hơn “seed giống nhau chưa?” là: **hai bộ sinh có đang ở cùng trạng thái trước lời gọi và sử dụng cùng phương thức/tham số không?**

## 3. Ví dụ Java 17 hoàn chỉnh với kết quả xác định

Tạo file `SeededRandomDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class SeededRandomDemo {
    private static List<Integer> generate(long seed, int count) {
        Random random = new Random(seed);
        List<Integer> values = new ArrayList<>();

        for (int i = 0; i < count; i++) {
            values.add(random.nextInt(100));
        }
        return values;
    }

    public static void main(String[] args) {
        List<Integer> first = generate(42L, 5);
        List<Integer> replay = generate(42L, 5);

        System.out.println("Seed 42: " + first);
        System.out.println("Replay identical: " + first.equals(replay));

        Random random = new Random(42L);
        System.out.println("Draw 1: " + random.nextInt(100));
        System.out.println("Draw 2: " + random.nextInt(100));

        random.setSeed(42L);
        System.out.println("After setSeed, draw 1: "
                + random.nextInt(100));

        Random restartedEachTime = new Random(42L);
        int fixedFirst = restartedEachTime.nextInt(100);
        int sameFirst = new Random(42L).nextInt(100);
        System.out.println("Two fresh generators: "
                + fixedFirst + ", " + sameFirst);

        Random anotherSeed = new Random(123L);
        Random replayAnotherSeed = new Random(123L);
        System.out.println("Seed 123 reproducible: "
                + (anotherSeed.nextLong()
                    == replayAnotherSeed.nextLong()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac SeededRandomDemo.java
java SeededRandomDemo
~~~

Kết quả:

~~~text
Seed 42: [30, 63, 48, 84, 70]
Replay identical: true
Draw 1: 30
Draw 2: 63
After setSeed, draw 1: 30
Two fresh generators: 30, 30
Seed 123 reproducible: true
~~~

Giải thích:

1. Hai lần `generate(42L, 5)` tạo hai đối tượng `Random` mới nhưng áp dụng **cùng seed và năm lời gọi `nextInt(100)` theo cùng thứ tự**, nên hai danh sách bằng nhau.
2. Một `Random` được sử dụng liên tục không trả mãi giá trị đầu tiên: lần gọi kế tiếp dùng trạng thái tiếp theo.
3. `setSeed(42L)` **thiết lập lại chuỗi** của đối tượng đó. Sau khi đặt lại cùng seed, lời gọi đầu tiên lại trả `30`.
4. Tạo `new Random(42L)` mỗi lần lặp sẽ **khởi động lại từ đầu**, nên dễ lấy lặp đi lặp lại giá trị `30`; đây là lỗi phổ biến khi muốn sinh nhiều số khác nhau.
5. Với seed 123, hai lời gọi `nextLong()` đầu tiên trên hai đối tượng mới cho cùng kết quả. Ví dụ chỉ kiểm tra tính tái lập, không cần ghi nhớ giá trị `long` thực tế.

Các giá trị trong ví dụ thuộc `java.util.Random`, không phải cam kết chung cho tất cả bộ sinh ngẫu nhiên khác trong Java.

## 4. Bên trong java.util.Random: seed quyết định chuỗi như thế nào?

Với lớp `java.util.Random` cổ điển, thuật toán cốt lõi là một **linear congruential generator (LCG)** sử dụng trạng thái **48 bit**. Ở mức khái niệm, nó thực hiện:

~~~text
Trạng thái ban đầu 48 bit = (seed XOR 0x5DEECE66D) AND (2^48 - 1)

Trạng thái kế tiếp =
    (trạng thái hiện tại * 0x5DEECE66D + 0xB) mod 2^48

Kết quả đọc ra từ các bit cao của trạng thái mới.
~~~

Trong đặc tả `Random`, các chi tiết cập nhật trạng thái và cách phương thức lõi `next(int bits)` lấy bit được quy định, giúp chuỗi với cùng seed và cùng cách gọi có thể tái lập giữa những triển khai Java tương thích của **chính lớp này**.

Không nên tự triển khai LCG chỉ để gọi `nextInt`; hãy dùng API chuẩn. Nhưng hiểu cơ chế giúp giải thích một số tính chất:

- Cùng seed thiết lập cùng trạng thái ban đầu, nên cùng đường đi trạng thái nếu cùng cách tiêu thụ.
- Mỗi phương thức có thể tiêu thụ một hoặc nhiều lần cập nhật trạng thái.
- Seed đưa vào constructor có kiểu `long`, nhưng trạng thái cốt lõi chỉ có 48 bit. Hai seed chỉ khác ở các bit nằm ngoài 48 bit thấp có thể cho **cùng chuỗi**. Ví dụ `42L` và `42L + (1L << 48)` tạo cùng trạng thái ban đầu của `Random` chuẩn.
- Vì có không gian trạng thái hữu hạn và thuật toán có thể dự đoán, đây **không phải** bộ sinh thích hợp để tạo token bảo mật.

Khi nói “chuỗi cố định”, cần hiểu đó là **chuỗi thuật toán của một bộ sinh cụ thể**; cùng số seed đưa vào một thuật toán khác (ví dụ `SplittableRandom`) không có nghĩa cho các con số giống `Random`.

## 5. Thứ tự lời gọi quan trọng như seed

Một đối tượng `Random` có trạng thái biến đổi. Cách tiêu thụ nó ảnh hưởng các giá trị xuất hiện về sau.

~~~java
Random a = new Random(42L);
Random b = new Random(42L);

int aFirst = a.nextInt(100); // 30
int aSecond = a.nextInt(100); // 63

int bFirst = b.nextInt(100); // 30
// Nếu b được gọi thêm ở chỗ khác, các phép lấy sau đó sẽ
// không còn ứng với vị trí aSecond theo cách gọi này.
~~~

Lưu ý về các phương thức khác nhau:

| Phương thức | Ý nghĩa | Lưu ý về chuỗi |
| --- | --- | --- |
| `nextInt()` | Sinh một `int` từ toàn miền int | Tiêu thụ trạng thái |
| `nextInt(bound)` | Sinh `int` trong `[0, bound)` | Với bound không phải lũy thừa 2 có thể cần lấy lại để tránh độ lệch phân bố |
| `nextLong()` | Sinh một `long` | Thường kết hợp nhiều lần sinh bit bên trong |
| `nextDouble()` | Sinh `double` trong `[0.0, 1.0)` | Tiêu thụ các bit để tạo độ chính xác cho double |
| `nextBoolean()` | Sinh `true` hoặc `false` | Tiêu thụ trạng thái |
| `nextGaussian()` | Sinh giá trị phân bố chuẩn | Có cơ chế giữ lại một giá trị gaussian cho lần gọi sau, nên lịch sử gọi còn quan trọng hơn |

`nextInt(bound)` không nên được coi là **luôn** tiêu thụ đúng một bước trạng thái trong mọi trường hợp: thuật toán có thể phải thử lại nếu giá trị ứng viên nằm ngoài miền chấp nhận. `nextDouble()`, `nextLong()` và `nextGaussian()` cũng không được hiểu như cùng một lời gọi `nextInt()`.

Do đó, việc thay một `nextInt(100)` bằng `nextDouble()`, thêm một lời gọi debug, hoặc chuyển vị trí lấy số ngẫu nhiên trong chương trình có thể khiến **phần chuỗi tiếp theo khác với bản chạy trước** ngay cả khi seed giữ nguyên.

## 6. Seed giống nhau nhưng lời gọi khác: minh họa trạng thái

Giả sử một trò chơi sử dụng một `Random(42)` cho mọi quyết định. Bản đầu tiên:

~~~java
Random random = new Random(42L);
int enemyMove = random.nextInt(100);
int lootRoll = random.nextInt(100);
~~~

Bản sau có thêm thao tác lấy số trước khi tính `lootRoll`:

~~~java
Random random = new Random(42L);
int enemyMove = random.nextInt(100);
int weatherRoll = random.nextInt(100);
int lootRoll = random.nextInt(100);
~~~

Với ví dụ cụ thể này, `enemyMove` vẫn là `30`; `lootRoll` trước đó là `63`, còn sau khi thêm `weatherRoll` thì `lootRoll` là `48`. Không có lỗi ở `Random`: hai lần chạy đã **tiêu thụ chuỗi ở các vị trí khác nhau**.

Để mô phỏng nhiều phần tương đối độc lập (ví dụ thời tiết và chiến lợi phẩm), có thể cấp mỗi phần một `Random` riêng với seed được quản lý rõ ràng. Khi đó việc gọi thêm số ở phần thời tiết sẽ không tiến trạng thái của bộ sinh ở phần chiến lợi phẩm.

~~~java
Random weatherRandom = new Random(1001L);
Random lootRandom = new Random(2002L);
~~~

Các seed ở đây là ví dụ được chọn trước để dễ tái lập; không phải công thức bảo đảm hai chuỗi hoàn toàn độc lập về thống kê. Với bài toán mô phỏng lớn, hãy chọn chiến lược chia luồng sinh số và thuật toán phù hợp, đồng thời lưu rõ seed mỗi luồng.

## 7. setSeed(): phát lại từ đầu, không đảo ngược một bước

Một đối tượng đã phát nhiều giá trị có thể được khởi tạo lại:

~~~java
Random random = new Random(42L);

int first = random.nextInt(100);  // 30
int second = random.nextInt(100); // 63

random.setSeed(42L);

int replayFirst = random.nextInt(100); // 30
~~~

`setSeed(42L)` không “trừ một bước” từ trạng thái hiện tại. Nó **đặt lại trạng thái từ seed được cung cấp**. Điều đó có nghĩa là những lời gọi đã tiêu thụ trước đó không còn quyết định chuỗi sau khi reseed.

Riêng `Random.nextGaussian()` sử dụng bộ đệm để lưu một kết quả gaussian chưa trả ra; gọi `setSeed()` cũng xóa trạng thái bộ đệm này theo hợp đồng của lớp. Điều này quan trọng nếu cần replay chuỗi gaussian từ đầu.

Không nên gọi `setSeed` giữa các lần sinh số chỉ để “tăng độ ngẫu nhiên”. Reseed theo cùng giá trị liên tục sẽ làm chuỗi lặp lại từ đầu.

## 8. Seed do mình chọn và seed mặc định

Hai cách khởi tạo thường gặp:

~~~java
Random reproducible = new Random(2026L);
Random automatic = new Random();
~~~

**`new Random(2026L)`** dùng seed công khai, cố định do chương trình chọn. Khi thử nghiệm cần tái lập, hãy ghi lại seed và cách tiêu thụ các số.

**`new Random()`** dùng cơ chế seed khởi tạo tự động của Java. Hai lần tạo đối tượng có thể có seed khác nhau và chuỗi khác nhau, nhưng chương trình không nên dựa vào đó như một bảo đảm về bí mật, tính duy nhất tuyệt đối hoặc chất lượng mật mã. Nếu không ghi lại các điều kiện để tạo lại trạng thái, sẽ khó phát lại đúng một lần chạy.

Dùng `System.currentTimeMillis()` làm seed có thể tiện khi chạy thí nghiệm nhanh, nhưng nhiều lần tạo bộ sinh trong cùng một mili giây có thể nhận cùng seed. Với kiểm thử tự động, một seed cố định thường dễ điều tra lỗi hơn.

Một thực hành hữu ích là **in hoặc lưu seed của lần chạy gây lỗi**, kèm mã phiên bản và các tùy chọn ảnh hưởng số lần gọi. Khi lỗi chỉ xảy ra ở một kịch bản ngẫu nhiên, chạy lại với cùng dữ liệu giúp tái hiện.

## 9. Sinh số trong khoảng và tránh các bẫy

`random.nextInt(bound)` yêu cầu `bound > 0` và trả số trong khoảng nửa mở `[0, bound)`. Nếu `bound <= 0`, phương thức ném `IllegalArgumentException`.

~~~java
Random random = new Random(42L);
int die = random.nextInt(6) + 1; // 1..6
~~~

Muốn lấy số nguyên từ `min` đến `max` **bao gồm cả hai đầu** và biết chắc phép tính không tràn int:

~~~java
int value = min + random.nextInt(max - min + 1);
~~~

Đây chỉ là **mẫu biểu thức** khi `min`, `max` và độ rộng khoảng hợp lệ, hiệu `max - min + 1` nằm trong miền `int`. Với khoảng rộng, có thể dùng API nhận origin/bound phù hợp trên Java hiện đại hoặc tính bằng `long`, và phải kiểm tra biên trên có tràn hay không.

Java 17 cung cấp các API từ `RandomGenerator`, nhưng đừng tự động suy ra rằng một lời gọi API khác sẽ tiêu thụ trạng thái đúng như công thức `nextInt(bound)` cũ. Muốn replay chính xác, nên giữ cố định cách gọi và phiên bản chương trình.

Một điều nữa: seed cố định không biến năm số đầu thành “mẫu đều” trên miền 0..99. Tính tái lập của chuỗi và đánh giá phân bố thống kê là hai bài toán khác nhau. Không đánh giá tính đúng của PRNG bằng cách đòi mỗi số trong một đoạn ngắn xuất hiện đúng một lần.

## 10. Random, ThreadLocalRandom, SplittableRandom và SecureRandom

Các lớp liên quan giải quyết những nhu cầu khác nhau.

| Lớp/API | Tình huống thường dùng | Lưu ý với seed |
| --- | --- | --- |
| `java.util.Random` | Ví dụ, kiểm thử và mô phỏng đơn giản cần tái lập | Nhận seed tường minh; chuỗi thuật toán `Random` truyền thống được quy định |
| `java.util.SplittableRandom` | Sinh số cho tác vụ mô phỏng có thể chia nhỏ | Có constructor nhận seed, nhưng **thuật toán/chuỗi khác `Random`** |
| `java.util.concurrent.ThreadLocalRandom` | Sinh số thuận tiện trong nhiều luồng | Lấy bằng `current()`; không hỗ trợ `setSeed` bên ngoài để replay như `Random` |
| `java.security.SecureRandom` | Token, salt, nonce và dữ liệu cần tính khó dự đoán | Dành cho mục đích an toàn mật mã; cách seed/thuật toán phụ thuộc triển khai, không dùng như công cụ replay chuỗi `Random` |

`Random` có thể được dùng bởi nhiều luồng, nhưng **thứ tự thực tế của các lời gọi** từ các luồng có thể thay đổi do lập lịch. Vì vậy **cùng seed không đủ bảo đảm mỗi luồng nhận đúng cùng dãy giá trị** nếu các luồng chia sẻ một bộ sinh và chạy xen kẽ khác nhau.

`ThreadLocalRandom.current().setSeed(...)` không phải cách đặt seed hợp lệ cho trình sinh số của luồng: `setSeed` được thiết kế để ném `UnsupportedOperationException`. Với yêu cầu tái lập độc lập từng luồng, thiết kế phân chia seed/bộ sinh cụ thể cho từng nhiệm vụ; cân nhắc `SplittableRandom` hoặc bộ sinh từ `java.util.random` theo hợp đồng dự án.

**Tuyệt đối không sử dụng `new Random(fixedSeed)` để tạo token đăng nhập, khóa, OTP hay giá trị bí mật.** Các giá trị đầu ra có thể dự đoán vì thuật toán và seed không được bảo vệ cho nhu cầu này. Dùng `SecureRandom` và áp dụng hướng dẫn bảo mật phù hợp.

## 11. Streams, số lần tiêu thụ và tái lập

`Random` còn hỗ trợ tạo stream số nguyên:

~~~java
Random random = new Random(42L);

List<Integer> values = random.ints(5, 0, 100)
        .boxed()
        .toList();
~~~

Trong Java 17, `toList()` của Stream trả danh sách theo encounter order của stream có thứ tự. Ở ví dụ trên, ta tạo năm số nguyên trong `[0, 100)` từ bộ sinh được đặt seed.

Điểm quan trọng: stream tiêu thụ chính đối tượng `random`. Nếu gọi thêm `random.nextInt()` trước khi xử lý stream, kết quả lấy được có thể thay đổi. Nếu cần kết quả kiểm thử dễ đối chiếu, tiêu thụ stream theo thứ tự tuần tự và cố định những lời gọi ngoài stream.

Không nên giả định rằng chia sẻ một bộ sinh giữa các stream song song, các task đa luồng hoặc thay đổi cấu trúc pipeline sẽ giữ nguyên ánh xạ số ngẫu nhiên đến từng phần tử. Kết quả phụ thuộc cách tiêu thụ, và lịch trình thực thi có thể không được xác định.

## 12. Kiểm thử tái lập với một seed cố định

Với một thuật toán dùng số ngẫu nhiên, thay vì rải các lời gọi `new Random()` khắp nơi, có thể nhận một `Random` như tham số:

~~~java
static int rollDie(Random random) {
    return random.nextInt(6) + 1;
}
~~~

Đây là **mảnh phương thức** trong lớp Java có `import java.util.Random;`.

Ưu điểm: mã gọi kiểm soát được seed và trạng thái, giúp kiểm thử tái lập. Ví dụ:

~~~java
Random experiment = new Random(500L);
int firstRoll = rollDie(experiment);
int secondRoll = rollDie(experiment);
~~~

Nếu cần phát lại, tạo một `Random(500L)` mới và gọi `rollDie` hai lần cùng thứ tự. Để so sánh hai triển khai, có thể tạo **hai đối tượng riêng** có cùng seed, rồi đảm bảo cả hai triển khai tiêu thụ cùng số lần và kiểu lời gọi. Nếu thuật toán mới có thêm một lần rút số, phải xác định đó là thay đổi có chủ ý trước khi so sánh kết quả từng bước.

Khi ghi log để tái lập lỗi, những thông tin hữu ích thường gồm: **seed**, **lớp/thuật toán PRNG**, **phiên bản mã**, **tham số sinh số (như bound)** và **trình tự các sự kiện tiêu thụ**. Với chạy song song, nên bổ sung cách phân phối seed và thứ tự xử lý công việc.

## 13. Lỗi thường gặp

**Lỗi 1 — Tạo `new Random(42L)` trong mỗi vòng lặp.** Mỗi đối tượng khởi đầu tại vị trí đầu chuỗi, nên gọi `nextInt(100)` đầu tiên đều được `30`. Đúng hơn là khởi tạo một đối tượng ngoài vòng lặp rồi sử dụng liên tục.

**Lỗi 2 — Nghĩ seed giống nhau là đủ.** Nếu một nhánh code thực hiện thêm `nextInt`, `nextLong`, `nextDouble`, hoặc `nextGaussian`, các vị trí tiêu thụ không còn tương ứng; cùng seed cũng không bảo đảm kết quả ở bước nghiệp vụ tương ứng giống nhau.

**Lỗi 3 — Dùng `nextInt(10)` rồi kỳ vọng có số 10.** Bound là **exclusive**. `nextInt(10)` chỉ trả 0..9. Để sinh xúc xắc 1..6, dùng `nextInt(6) + 1`.

**Lỗi 4 — Cho bound bằng 0 hoặc âm.** `nextInt(0)` và `nextInt(-3)` ném `IllegalArgumentException`; phải kiểm tra điều kiện đầu vào.

**Lỗi 5 — Trộn kết quả nhiều luồng và mong replay y nguyên.** Cùng seed cho một đối tượng chia sẻ không cố định thứ tự xen kẽ giữa các luồng. Thiết kế một bộ sinh cho mỗi tác vụ với seed quản lý độc lập khi cần tái lập.

**Lỗi 6 — Dùng `Random` cho mã bảo mật.** Seed có thể bị suy đoán và trạng thái LCG chỉ có 48 bit; dùng `SecureRandom` cho giá trị cần khó đoán.

**Lỗi 7 — Chỉ lưu seed nhưng không lưu thuật toán hoặc thứ tự tiêu thụ.** Khi đổi loại PRNG, thay đổi bound hay thêm lần gọi, dãy số có thể khác. Log cần có đủ ngữ cảnh để tái hiện.

**Lỗi 8 — Giả định mọi seed `long` đều sinh một chuỗi duy nhất.** Đối với `java.util.Random` chuẩn, seed được biến đổi rồi giới hạn về 48 bit; có những seed `long` khác nhau cho cùng chuỗi.

**Lỗi 9 — Đồng nhất “giống chuỗi” với “đảm bảo phân bố tốt trong mọi tình huống”.** Tái lập không chứng minh tính đều hay tính độc lập thống kê. Nếu kết quả mô phỏng đòi hỏi chất lượng thống kê cao, lựa chọn thuật toán phải được đánh giá riêng.

## 14. Bài luyện tập tự kiểm tra

**Câu 1.** Chương trình sau in gì?

~~~java
Random a = new Random(42L);
Random b = new Random(42L);

System.out.println(a.nextInt(100));
System.out.println(b.nextInt(100));
System.out.println(a.nextInt(100));
~~~

**Đáp án:**

~~~text
30
30
63
~~~

Mỗi đối tượng giữ trạng thái riêng. Hai lời gọi đầu lấy số đầu tiên của hai chuỗi giống nhau; lời gọi cuối là số thứ hai của `a`.

**Câu 2.** Nếu thêm một lời gọi `nextInt(100)` vào trước phần tính kết quả của một mô phỏng, seed có đổi không? Kết quả về sau có thể đổi không?

**Đáp án:** Seed ban đầu không đổi, nhưng trạng thái đã tiến thêm. Vì vậy những số mà các bước sau nhận được có thể thay đổi.

**Câu 3.** Hai `Random` được tạo bằng `new Random(42L)` và `new Random(42L + (1L << 48))` có cho cùng chuỗi `nextInt(100)` không?

**Đáp án:** Có, đối với thuật toán 48 bit của `java.util.Random` được mô tả ở trên: phần chênh lệch nằm ngoài 48 bit thấp nên trạng thái ban đầu tương đương.

**Câu 4.** Muốn tái hiện một bug chỉ xảy ra với dữ liệu giả ngẫu nhiên, tối thiểu cần ghi gì ngoài seed?

**Đáp án:** Bộ sinh và phiên bản/hành vi chương trình, cùng những phương thức và tham số tiêu thụ chuỗi theo đúng thứ tự. Nếu có song song, cần kiểm soát việc phân chia chuỗi và lịch trình hoặc ghi thông tin đủ để tái hiện.

**Câu 5.** Có nên dùng `Random(42L)` để tạo mã xác thực 6 chữ số cho người dùng không?

**Đáp án:** Không. Seed cố định dẫn đến chuỗi có thể tái lập và `Random` không phải bộ sinh mật mã. Hãy dùng `SecureRandom` cho trường hợp cần khó đoán.

**Ghi nhớ:** Seed là điểm khởi đầu của một **chuỗi giả ngẫu nhiên có trạng thái**. Với `java.util.Random`, cùng seed, cùng cách gọi và cùng thứ tự tiêu thụ cho cùng kết quả; `setSeed` khởi tạo lại chuỗi. Dùng đặc tính này để tái lập kiểm thử/mô phỏng, đồng thời nhớ giới hạn về đa luồng, thay đổi thuật toán và bảo mật.
