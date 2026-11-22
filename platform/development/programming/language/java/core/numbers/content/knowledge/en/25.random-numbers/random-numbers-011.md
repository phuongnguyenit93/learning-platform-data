# Chọn thuật toán, seed và cách kiểm thử số ngẫu nhiên trong Java: phân biệt tái lập với bảo mật

## 1. Ba câu hỏi cần tách riêng

Khi một chương trình cần sinh số ngẫu nhiên, không thể chọn API chỉ dựa trên việc nó trả về số trông có vẻ khó đoán. Trước tiên, hãy xác định:

1. **Dùng vào việc gì?** Mô phỏng, dữ liệu kiểm thử, chọn mẫu, trò chơi, phân tải, hay tạo token/giá trị bí mật?
2. **Có cần chạy lại đúng kết quả không?** Một thí nghiệm hoặc lỗi phát sinh từ số giả ngẫu nhiên thường cần tái lập bằng seed và cùng thứ tự gọi.
3. **Có cần chống kẻ tấn công dự đoán không?** Token phiên đăng nhập, mã đặt lại mật khẩu, khóa bí mật và các giá trị nhạy cảm phải được sinh bởi bộ sinh ngẫu nhiên an toàn mật mã (CSPRNG) phù hợp.

Ba tính chất **có thể kiểm thử được**, **có phân bố thích hợp** và **khó dự đoán trước đối thủ** là các yêu cầu khác nhau. Một danh sách có vẻ lộn xộn không chứng minh an toàn; một chuỗi tái lập chính xác càng không phải bằng chứng an toàn. Seed là thành phần khởi tạo bộ sinh, nhưng không tự biến một thuật toán thành CSPRNG.

Mục tiêu của bài là lựa chọn đúng công cụ Java 17+, quản lý seed có chủ đích, thiết kế kiểm thử đáng tin và tránh những suy luận sai về bảo mật.

## 2. Bản chất pseudorandom, seed và trạng thái

Một bộ sinh số giả ngẫu nhiên (PRNG) là thuật toán có **trạng thái**. Seed được dùng để thiết lập trạng thái ban đầu. Sau mỗi thao tác lấy số, trạng thái được cập nhật; các kết quả tiếp theo phụ thuộc vào trạng thái đó.

~~~text
seed ban đầu
    |
    v
trạng thái S0
    | nextInt(...) hoặc phương thức sinh số
    v
giá trị 1 + trạng thái S1
    | lần lấy tiếp theo
    v
giá trị 2 + trạng thái S2
    |
    v
...
~~~

Đối với một thuật toán xác định, nếu cùng trạng thái ban đầu và thực hiện **cùng trình tự gọi với cùng tham số**, ta có thể tái lập dãy kết quả. Thế nhưng:

- **Cùng seed nhưng khác thuật toán:** không bảo đảm cùng chuỗi.
- **Cùng thuật toán/seed nhưng khác số lần gọi:** các giá trị được gán cho từng bước nghiệp vụ có thể thay đổi.
- **Chia sẻ bộ sinh qua nhiều luồng:** thứ tự luồng tiêu thụ số có thể thay đổi giữa hai lần chạy.
- **Cùng seed nhưng khác phiên bản triển khai:** chỉ dựa vào tính tái lập giữa phiên bản khi hợp đồng cụ thể của bộ sinh bảo đảm điều đó.

Tính tái lập là công cụ để thử nghiệm và chẩn đoán. Tính an toàn mật mã là yêu cầu riêng đối với thuật toán, seed/nguồn entropy, cách dùng và môi trường vận hành.

## 3. Các lựa chọn trong Java 17+

| Công cụ | Phạm vi phù hợp | Seed và tái lập | Giới hạn chính |
| --- | --- | --- | --- |
| `java.util.Random` | Ví dụ, kiểm thử, mô phỏng nhỏ, mã cần tính tương thích với bộ sinh cổ điển | `new Random(long seed)`; cùng chuỗi khi cùng lời gọi; thuật toán cốt lõi của lớp được quy định | Không dùng cho bí mật; dùng chung nhiều luồng có thể tranh chấp và thay đổi thứ tự tiêu thụ |
| `java.util.SplittableRandom` | Mô phỏng cần nhiều luồng sinh số riêng hoặc chia công việc | Constructor nhận seed; có `split()` tạo bộ sinh mới | Không phải CSPRNG; đừng chia sẻ tùy tiện một thể hiện giữa nhiều luồng |
| `java.util.concurrent.ThreadLocalRandom` | Sinh số thông thường thuận tiện trong tác vụ chạy đồng thời | Lấy bằng `ThreadLocalRandom.current()`; không thiết kế để seed thủ công cho từng test | `setSeed(...)` không được hỗ trợ; không phù hợp khi cần tái lập từng chuỗi chính xác bằng seed do test cung cấp |
| `java.util.random.RandomGenerator` và `RandomGeneratorFactory` | Chọn thuật toán cụ thể, thiết kế API nhận bộ sinh từ bên ngoài | Có thể tạo bộ sinh từ tên thuật toán và seed khi factory hỗ trợ | Cần ghi rõ **tên thuật toán**, đặc tính và phiên bản môi trường khi cần replay lâu dài |
| `java.security.SecureRandom` | Token, nonce, salt và giá trị cần khó dự đoán | Thường khởi tạo không truyền seed cố định; hành vi seed và thuật toán phụ thuộc provider | Không coi `setSeed(fixedValue)` là hợp đồng replay; không thay bằng `Random` chỉ để dễ test |

Trong Java 17, `Random`, `SplittableRandom` và `ThreadLocalRandom` thuộc hệ sinh thái `RandomGenerator`. Phân loại ở trên không có nghĩa mọi thuật toán cung cấp cùng chuỗi cho một seed hay có cùng đặc tính thống kê.

**Nguyên tắc chọn nhanh:**

- Cần chuỗi xác định để kiểm thử/mô phỏng đơn giản → chọn `Random` với seed rõ ràng, hoặc một thuật toán xác định đã được ghi tên.
- Cần luồng sinh riêng cho những tác vụ mô phỏng → cân nhắc `SplittableRandom` hoặc những generator hỗ trợ tách/splitting, cấp seed và cấu trúc công việc minh bạch.
- Chỉ cần các giá trị không dùng vào bảo mật trong tác vụ đa luồng và không phải replay theo seed → `ThreadLocalRandom` thường tiện.
- Giá trị có ý nghĩa **bảo mật** → chọn `SecureRandom`; seed cố định và `Random` không phải thay thế hợp lệ.

## 4. Ví dụ Java 17: tái lập số kiểm thử và giữ ranh giới bảo mật

Tạo tệp `RandomChoiceDemo.java`:

~~~java
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.SplittableRandom;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class RandomChoiceDemo {
    static List<Integer> sample(Random random, int count) {
        List<Integer> numbers = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            numbers.add(random.nextInt(100));
        }
        return numbers;
    }

    static int rollDie(RandomGenerator random) {
        return random.nextInt(1, 7);
    }

    public static void main(String[] args) {
        List<Integer> run1 = sample(new Random(42L), 5);
        List<Integer> run2 = sample(new Random(42L), 5);

        System.out.println("Seed 42: " + run1);
        System.out.println("Same sequence: " + run1.equals(run2));

        Random stateful = new Random(42L);
        System.out.println("First: " + stateful.nextInt(100));
        System.out.println("Second: " + stateful.nextInt(100));
        stateful.setSeed(42L);
        System.out.println("After reset: " + stateful.nextInt(100));

        RandomGenerator g1 = RandomGeneratorFactory
                .of("L64X128MixRandom")
                .create(2026L);
        RandomGenerator g2 = RandomGeneratorFactory
                .of("L64X128MixRandom")
                .create(2026L);
        System.out.println("Named algorithm replay: "
                + (rollDie(g1) == rollDie(g2)));

        SplittableRandom left = new SplittableRandom(123L);
        SplittableRandom right = new SplittableRandom(123L);
        System.out.println("Splittable seeded replay: "
                + (left.nextLong() == right.nextLong()));

        SecureRandom secure = new SecureRandom();
        byte[] secretBytes = new byte[16];
        secure.nextBytes(secretBytes);
        System.out.println("Secure bytes count: " + secretBytes.length);
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac RandomChoiceDemo.java
java RandomChoiceDemo
~~~

Kết quả:

~~~text
Seed 42: [30, 63, 48, 84, 70]
Same sequence: true
First: 30
Second: 63
After reset: 30
Named algorithm replay: true
Splittable seeded replay: true
Secure bytes count: 16
~~~

Giải thích theo từng phần:

1. `new Random(42L)` sinh `[30, 63, 48, 84, 70]` khi gọi `nextInt(100)` năm lần. Cùng seed và cùng cách gọi cho cùng danh sách.
2. `stateful.nextInt(100)` tiêu thụ trạng thái. Sau hai lần gọi, `setSeed(42L)` đặt lại điểm bắt đầu, nên lần tiếp theo trả `30`.
3. `RandomGeneratorFactory.of("L64X128MixRandom")` chọn rõ **thuật toán được cung cấp trong Java 17**, rồi `create(2026L)` tạo hai generator dùng cùng seed. Ví dụ kiểm tra tính tái lập của một lời gọi `nextInt(1, 7)`; nó không tuyên bố dãy này giống `Random(2026L)`.
4. Hai `SplittableRandom(123L)` nhận cùng seed, lấy `nextLong()` đầu tiên nên kết quả bằng nhau. Điều này chỉ chứng minh lần sinh có thể tái lập theo thuật toán, không chứng minh bí mật.
5. `SecureRandom` tạo 16 byte mà chương trình không in giá trị. Chỉ in **độ dài luôn xác định**; các byte thực tế không được kỳ vọng cố định hay dự đoán. Không đưa giá trị nhạy cảm vào stdout/log.

Phương thức `rollDie(RandomGenerator random)` là một ví dụ **tiêm bộ sinh số** (dependency injection đơn giản): logic nghiệp vụ không cần tự quyết định seed. Dùng giao diện giúp chọn generator tại nơi khởi tạo, nhưng vẫn phải tuân thủ yêu cầu của ứng dụng về thuật toán và bảo mật.

## 5. Tái lập cần nhiều hơn một con số seed

Một lần chạy có thể chỉ thực sự tái lập được khi giữ các điều kiện sau:

| Điều kiện | Tại sao cần |
| --- | --- |
| Tên lớp hoặc thuật toán generator | `Random` và `SplittableRandom` không cùng thuật toán |
| Giá trị seed | Khởi tạo trạng thái tương ứng |
| Thứ tự, số lần gọi, tham số bound/origin | Mỗi lời gọi tiêu thụ trạng thái; một số API tiêu thụ nhiều bước |
| Cách phân chia generator cho tác vụ | Tránh khác thứ tự tiêu thụ giữa các tác vụ |
| Mã và phiên bản chạy có liên quan | Thay đổi thuật toán nghiệp vụ có thể thay đổi nơi lấy số |
| Dữ liệu đầu vào và cấu hình | Các nhánh điều kiện khác nhau có thể gọi generator số lần khác nhau |

Ví dụ hai đoạn sau đều dùng `Random(42L)`, nhưng ánh xạ dãy số tới `loot` khác nhau:

~~~java
Random before = new Random(42L);
int enemy = before.nextInt(100); // 30
int loot = before.nextInt(100);  // 63
~~~

~~~java
Random after = new Random(42L);
int enemy = after.nextInt(100);   // 30
int weather = after.nextInt(100); // 63
int loot = after.nextInt(100);    // 48
~~~

Các đoạn trên là **mảnh mã minh họa**; để chạy độc lập cần đặt trong lớp/phương thức và import `java.util.Random`. Việc thêm một lần rút số cho thời tiết làm `loot` lấy một vị trí khác trong chuỗi. Seed không hề thay đổi.

Nếu nhiều phần của mô phỏng cần tách rời, cấp generator riêng cho từng phần với seed được quản lý:

~~~java
Random weatherRandom = new Random(1001L);
Random lootRandom = new Random(2002L);
~~~

Khi đó thao tác lấy thêm số thời tiết không làm tiến trạng thái của `lootRandom`. Tuy nhiên hai seed khác nhau **không tự bảo đảm** tính độc lập thống kê lý tưởng; các thuật toán và chiến lược phân chia stream phải phù hợp yêu cầu mô phỏng.

## 6. Seed cố định, seed tự động và giới hạn của java.util.Random

`Random` cổ điển sử dụng một bộ sinh đồng dư tuyến tính (LCG) với trạng thái **48 bit**. Seed dạng `long` được trộn thành trạng thái theo công thức:

~~~text
state0 = (seed XOR 0x5DEECE66D) AND ((1L << 48) - 1)
stateNext = (state * 0x5DEECE66D + 0xB) mod 2^48
~~~

Về mặt kết quả, seed `42L` và `42L + (1L << 48)` có cùng 48 bit thấp nên cho cùng trạng thái khởi tạo và cùng chuỗi `Random`. Điều này cũng cho thấy **không phải mọi seed `long` khác nhau đều tạo chuỗi khác nhau** đối với lớp này.

`new Random()` sử dụng cơ chế khởi tạo seed tự động, thích hợp khi không cần chủ động ấn định chuỗi; nó **không** là giải pháp bảo mật. `new Random(System.currentTimeMillis())` tạo seed dựa trên đồng hồ, thường dễ đoán và có thể trùng giữa các lần khởi tạo gần nhau. Không dùng ngày giờ hoặc các giá trị hiển nhiên để làm “bí mật” cho token.

Tại sao `Random` không an toàn cho bí mật?

- Thuật toán công khai, trạng thái hữu hạn và mục đích thiết kế là sinh số giả ngẫu nhiên thông thường.
- Một kẻ quan sát có đủ thông tin về đầu ra có thể suy luận về chuỗi, vì vậy không có bảo đảm chống dự đoán tương tự CSPRNG.
- Seed cố định giúp phát lại kết quả, tức là trái với yêu cầu token cần khó đoán và không được lặp lại có hệ thống.

Nhớ rằng **cùng seed → cùng chuỗi** của `Random` là điều hữu ích cho kiểm thử, không phải bằng chứng token đủ ngẫu nhiên trước một đối thủ.

## 7. Bảo mật: dùng SecureRandom đúng mục đích

Với yêu cầu tạo byte mật mã, token hoặc giá trị cần chống suy đoán, dùng `java.security.SecureRandom`:

~~~java
SecureRandom secureRandom = new SecureRandom();
byte[] token = new byte[32]; // 256 bit dữ liệu được sinh
secureRandom.nextBytes(token);
~~~

Đây là mảnh mã đặt trong lớp có import `java.security.SecureRandom`. Nó minh họa tạo **32 byte** bằng một CSPRNG, nhưng chưa bao gồm cách mã hóa token, lưu trữ, thời hạn hiệu lực, xác thực, chống lộ log hay quy trình sử dụng an toàn khác. Độ dài 32 byte tự nó không đủ chứng minh toàn bộ hệ thống an toàn.

Các nguyên tắc:

- Ưu tiên để **provider của Java và hệ điều hành** khởi tạo entropy/trạng thái thích hợp khi dùng `new SecureRandom()`; chọn thuật toán/provider cụ thể khi môi trường hoặc yêu cầu bảo mật quy định.
- Không dùng `new Random(seed)`, `SplittableRandom` hoặc `ThreadLocalRandom` để tạo token đăng nhập, khóa, salt hoặc nonce cần tính khó dự đoán.
- Không dùng một seed cố định để khiến giá trị `SecureRandom` trong môi trường thực chạy lặp lại. `SecureRandom.setSeed(...)` có ngữ nghĩa phụ thuộc provider và thường **bổ sung seed** vào trạng thái thay vì bảo đảm đặt lại trạng thái để replay; không nên khẳng định “cùng seed cho cùng chuỗi” với `SecureRandom`.
- Không ghi log seed/byte bí mật; cũng không in token thực vào log hay test output. Trong khi đó, seed của **mô phỏng không có bí mật** có thể được ghi lại để phục vụ debug.
- Tính an toàn phụ thuộc cả cách sử dụng giá trị ngẫu nhiên: ngữ cảnh, vòng đời, số lượng, lưu trữ, điều kiện duy nhất và hệ thống phân quyền.

Nếu nghiệp vụ yêu cầu token 6 chữ số, một CSPRNG có thể chọn một giá trị số trong khoảng `0` đến `999_999` rồi định dạng đủ sáu chữ số; tuy nhiên token ngắn có ít khả năng thử hơn nên vẫn phải có thời hạn, giới hạn số lần thử và biện pháp phòng thủ thích hợp. Không suy ra “SecureRandom” tự giải quyết toàn bộ những vấn đề đó.

## 8. Những kiểm thử cần thiết cho bộ sinh số

Có ít nhất bốn nhóm mục tiêu kiểm thử, với tiêu chí khác nhau.

### 8.1. Kiểm thử tái lập (reproducibility)

Đối với `Random` với seed cố định:

~~~java
Random a = new Random(42L);
Random b = new Random(42L);

for (int i = 0; i < 100; i++) {
    if (a.nextInt(1000) != b.nextInt(1000)) {
        throw new AssertionError("Different sequences");
    }
}
~~~

Mảnh mã này minh họa kỳ vọng hai đối tượng cùng seed và cùng 100 lời gọi sẽ trùng nhau; đặt trong một phương thức/lớp có import `Random`.

Kiểm thử được ích lợi về tính tái lập và giúp phát hiện thay đổi trong cách mã đang tiêu thụ bộ sinh. Nó **không** kiểm thử chất lượng thống kê hay an toàn mật mã.

### 8.2. Kiểm thử thuộc tính và biên

Với hàm `rollDie(RandomGenerator)` trả số nguyên trong `[1,7)`, có thể kiểm tra **mọi kết quả quan sát** nằm trong `1..6`; với `nextInt(bound)`, bound phải dương. Kiểm thử có giá trị hơn khi xác minh logic sử dụng generator, ví dụ:

- Kết quả không vượt biên và không dưới cận.
- Với bound không hợp lệ, chương trình ném exception thích hợp.
- Không tạo một `Random(fixedSeed)` mới ngay trong mỗi lần rút nếu mục đích là tiêu thụ chuỗi liên tục.
- Nếu nghiệp vụ là xáo trộn danh sách, kết quả là hoán vị hợp lệ, không làm mất hay nhân đôi phần tử.

Không kiểm thử “100 lần chắc chắn phải có đủ cả sáu mặt xúc xắc” vì điều này là một biến cố xác suất, không phải bảo đảm toán học ở mẫu hữu hạn.

### 8.3. Kiểm thử phân bố thống kê

Với mô phỏng, việc kiểm tra tính đều, sai lệch, sự tương quan hoặc chất lượng thuật toán cần phương pháp thống kê phù hợp. Một kiểm thử thô như đếm tần suất sau 20 lần lấy số không đủ kết luận. Các kiểm định phân bố có **xác suất báo động nhầm** và có thể bỏ sót lỗi; không biến chúng thành tiêu chí “100% phải vượt mọi lần chạy” mà không thiết kế ngưỡng và kích thước mẫu cẩn thận.

Với hệ thống quan trọng, có thể kết hợp bộ kiểm định thống kê đã được đánh giá, phân tích đặc tính thuật toán, seed đa dạng và thí nghiệm tái lập. Thống kê về sự đều không thay thế đánh giá bảo mật của CSPRNG.

### 8.4. Kiểm thử hệ thống sử dụng SecureRandom

Một chương trình an toàn không nên viết test kiểu:

~~~java
SecureRandom secure = new SecureRandom();
secure.setSeed(42L);
// Sai mục đích: đòi chuỗi byte bảo mật phải cố định trên mọi provider.
~~~

Vì `SecureRandom` không cung cấp hợp đồng replay chung khi truyền seed theo cách này, việc cố định byte kết quả dễ làm test phụ thuộc provider hoặc cám dỗ thay CSPRNG bằng PRNG thường.

Thay vào đó, kiểm thử **hành vi của ứng dụng**: token có đúng số byte/ký tự, API sử dụng nguồn CSPRNG đã được chọn, cơ chế xác thực và hết hạn hoạt động đúng, lỗi được xử lý, dữ liệu bí mật không vô tình ghi ra ngoài. Với unit test có nhu cầu tách phụ thuộc, dùng một lớp trừu tượng hóa hoặc fake nguồn sinh số trong phạm vi test để điều khiển dữ liệu đầu vào; cấu hình production vẫn dùng `SecureRandom`.

## 9. Thiết kế để dễ kiểm thử: truyền generator vào logic nghiệp vụ

Một hàm trực tiếp tạo `new Random()` bên trong khó tái lập hành vi và dễ làm kết quả kiểm thử không ổn định:

~~~java
// Minh họa điểm bất tiện: trạng thái được khởi tạo bên trong hàm.
static int randomIndex(int size) {
    return new Random().nextInt(size);
}
~~~

Đoạn trên là **mảnh phương thức**. Nếu cần deterministic test, tách lựa chọn generator ra khỏi logic:

~~~java
static int randomIndex(RandomGenerator rng, int size) {
    if (size <= 0) {
        throw new IllegalArgumentException("size must be positive");
    }
    return rng.nextInt(size);
}
~~~

Ví dụ ở Java 17 với `import java.util.random.RandomGenerator;`. Test có thể truyền `new Random(42L)` và kiểm tra chỉ số rút ra; mã sử dụng generator được cung cấp có thể cấu hình khác theo nhu cầu. Không đặt `new Random(42L)` cố định trong code production của một chức năng yêu cầu giá trị khó đoán.

Nếu hàm sinh token, nên tách cấu trúc token khỏi nguồn byte ngẫu nhiên và ép đường production dùng `SecureRandom`/dịch vụ tương đương đã cấu hình đúng. Việc tiêm dependency không được vô tình mở đường dùng bộ sinh không an toàn cho chức năng nhạy cảm.

Một kiểm thử tốt thường có hai tầng:

1. **Unit test logic** dùng đầu vào giả/điều khiển được để kiểm tra định dạng, ranh giới và xử lý lỗi.
2. **Integration/security validation** kiểm tra cấu hình thực tế sử dụng CSPRNG theo yêu cầu, cùng các kiểm soát bảo mật xung quanh.

Không cần “dự đoán đúng byte SecureRandom sẽ sinh” để chứng minh logic gọi API đúng.

## 10. Đa luồng và lựa chọn chiến lược seed

Trong mô phỏng song song, chỉ cấp một `Random(42L)` dùng chung cho mọi luồng không đủ bảo đảm từng tác vụ sẽ nhận cùng dữ liệu trong mỗi lần chạy. Nếu luồng A và B gọi xen kẽ theo thứ tự khác, các giá trị được gán cho A/B cũng khác. Tính an toàn trong tương tác nhiều luồng và tính tái lập theo **tác vụ** là hai điều riêng.

Một chiến lược để kiểm thử:

- Gán mỗi tác vụ một **mã định danh ổn định**.
- Ánh xạ mã đó tới seed riêng theo một quy tắc đã thiết kế và ghi lại.
- Tạo generator riêng bên trong tác vụ; tránh phụ thuộc thứ tự scheduler lấy số.
- Nếu dùng `SplittableRandom.split()`, việc chia các generator thành cây cũng phải được thực hiện theo **cấu trúc và thứ tự ổn định** nếu muốn tái lập chính xác kết quả từng tác vụ.

Không mặc định các seed như `baseSeed + taskIndex` cho những chuỗi độc lập về thống kê một cách hoàn hảo; cần chọn phương án seeding và generator phù hợp với chất lượng mô phỏng yêu cầu. Nếu dùng `ThreadLocalRandom`, cần chấp nhận rằng API không hỗ trợ đặt seed của từng luồng qua `setSeed` để phát lại như `Random`.

Trong Java 17, `RandomGeneratorFactory` hỗ trợ lựa chọn thuật toán theo tên hoặc thuộc tính; hãy kiểm tra thuật toán thực sự có sẵn trong runtime và ghi lại lựa chọn khi cần tái lập dài hạn. Không phải mọi generator có cùng đặc tính phân bố, phân tách và hiệu năng.

## 11. Khi nào seed là dữ liệu nên ghi, khi nào không?

Với **kiểm thử/mô phỏng không nhạy cảm**, ghi seed thường là thực hành tốt:

~~~text
simulation=inventory-replay
prng=java.util.Random
seed=42
draws=5 x nextInt(100)
result=[30, 63, 48, 84, 70]
~~~

Ví dụ log này không chứa bí mật và cho người khác thông tin cần để kiểm tra lại kết quả. Nếu chương trình thay đổi nhánh xử lý, cần ghi thêm phiên bản hoặc các sự kiện sử dụng số ngẫu nhiên.

Với **giá trị phục vụ bảo mật**, tình huống khác hoàn toàn: seed hoặc trạng thái nội bộ có thể là thông tin bí mật; không ghi lại hay chia sẻ để “tái lập token”. Chỉ log thông tin vận hành cần thiết và đã được kiểm soát, chẳng hạn sự kiện phát hành token thành công, mã tương quan không nhạy cảm hoặc thời điểm hết hạn, theo chính sách bảo mật.

Tránh trộn quy tắc quan sát của test và production. Kể cả khi một seed không nhạy cảm ở môi trường thử nghiệm, việc tái sử dụng chính seed này để tạo token thực vẫn sai mục đích.

## 12. Những lỗi phổ biến

**Lỗi 1 — “Cùng seed tức là đủ bảo đảm cùng dữ liệu.”** Sai nếu thay thuật toán, đổi thứ tự gọi, bổ sung lần rút số hoặc để nhiều luồng tranh cùng một generator. Cần ghi cả ngữ cảnh tiêu thụ.

**Lỗi 2 — “Đã cố định seed, vậy token sẽ an toàn.”** Seed cố định làm kết quả dễ tái lập. Thuật toán `Random` không có bảo đảm an toàn mật mã; dùng `SecureRandom` cho bí mật.

**Lỗi 3 — “SecureRandom có setSeed nên test có thể khôi phục cùng chuỗi ở mọi máy.”** Không có hợp đồng chung như vậy. Provider có thể có thuật toán và cơ chế bổ sung seed khác nhau.

**Lỗi 4 — “Khác seed phải khác mọi số.”** Hai chuỗi có thể trùng một vài kết quả ngẫu nhiên; với `Random` 48 bit, nhiều seed `long` còn có thể dẫn đến cùng trạng thái ban đầu. Không dùng “mỗi lần tạo generator phải ra số đầu tiên khác” như một phép kiểm thử đúng/sai.

**Lỗi 5 — Gọi `new Random(seed)` trong vòng lặp.** Mỗi đối tượng bắt đầu lại ở đầu chuỗi, dễ tạo cùng số đầu tiên lặp nhiều lần. Nếu cần một chuỗi, tạo một đối tượng rồi tiêu thụ liên tục.

**Lỗi 6 — Nhầm khoảng của `nextInt(bound)`.** `nextInt(6)` sinh 0..5; xúc xắc 1..6 cần cộng 1 hoặc dùng `nextInt(1, 7)` ở API hỗ trợ.

**Lỗi 7 — Kiểm thử phân bố bằng một số ít lần rút.** Một mẫu ngắn có thể lệch tự nhiên. Cần kiểm định thống kê có thiết kế phù hợp, không áp quy tắc tùy tiện.

**Lỗi 8 — Dùng `ThreadLocalRandom.setSeed` để tái lập.** API chủ đích không hỗ trợ đặt seed sau khi lấy instance; việc gọi sẽ ném `UnsupportedOperationException`.

**Lỗi 9 — Không phân biệt log seed mô phỏng và log bí mật.** Ghi seed cho mô phỏng thông thường giúp debug; ghi seed/trạng thái CSPRNG hoặc token bí mật có thể làm lộ hệ thống.

**Lỗi 10 — Đổi bộ sinh để tăng tốc mà không xem lại các giả định.** Kết quả, chất lượng thống kê, khả năng tách luồng và tính tương thích của replay có thể đổi; cần đánh giá theo yêu cầu.

## 13. Bài luyện tập có lời giải

### Bài 1. Chọn bộ sinh theo tình huống

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Sinh năm số kiểm thử cần phát lại chính xác | `new Random(42L)` và cùng lời gọi | Thuận tiện kiểm thử xác định |
| Mô phỏng lớn cần generator riêng cho các nhánh | `SplittableRandom` hoặc generator hỗ trợ split | Có thể phân chia bộ sinh và quản lý trạng thái theo tác vụ |
| Tác vụ đa luồng cần số thông thường, không cần đặt seed | `ThreadLocalRandom.current()` | Phù hợp cách dùng theo luồng |
| Tạo token khôi phục tài khoản | `SecureRandom` | Yêu cầu nguồn sinh khó dự đoán |
| Chọn thuật toán có tên để quản lý cấu hình thí nghiệm | `RandomGeneratorFactory.of(name)` | Chọn thuật toán rõ ràng, ghi nhận để replay |

**Điểm đánh giá:** Lựa chọn chỉ hợp lý khi đi kèm các yêu cầu về replay, phân bố và bảo mật; không có một bộ sinh tối ưu cho tất cả bài toán.

### Bài 2. Dự đoán kết quả khi gọi cùng seed

~~~java
Random a = new Random(42L);
Random b = new Random(42L);

System.out.println(a.nextInt(100));
System.out.println(a.nextInt(100));
System.out.println(b.nextInt(100));
~~~

Đáp án:

~~~text
30
63
30
~~~

Vì `a` đã tiêu thụ hai vị trí, còn `b` mới tiêu thụ vị trí đầu tiên.

### Bài 3. Sửa một test không ổn định

Giả sử `calculateDiscount()` gọi `new Random()` bên trong, khiến test không biết bộ sinh sẽ đưa về giá trị nào. Hãy sửa thiết kế để hàm nhận `RandomGenerator` hoặc một giao diện cung cấp giá trị ngẫu nhiên từ ngoài. Trong test, truyền bộ sinh với seed đã biết; trong production, cấu hình bộ sinh phù hợp với yêu cầu nghiệp vụ. Nếu giảm giá phải chống người dùng dự đoán để khai thác, hãy thiết kế kiểm soát nghiệp vụ và nguồn ngẫu nhiên an toàn chứ không chỉ thay seed.

### Bài 4. Phân tích một lời khẳng định

“Dãy token sinh ra đã vượt kiểm định tần suất, nên chắc chắn khó đoán.”

**Đáp án:** Không đúng. Một thuật toán xác định đơn giản có thể cho tần suất trông đều mà vẫn đoán được khi biết seed hoặc trạng thái. Kiểm định tần suất không thay thế phân tích và lựa chọn CSPRNG.

### Bài 5. Ghi nhật ký tái lập

Một lỗi xuất hiện sau khi chia mô phỏng thành bốn tác vụ chạy song song. Chỉ ghi `seed=100` có đủ không?

**Đáp án:** Chưa đủ. Cần biết generator/thuật toán, cách gán hoặc split seed cho từng tác vụ, thứ tự tiêu thụ số (hoặc cách tách trạng thái độc lập), phiên bản chương trình và đầu vào. Nếu mỗi tác vụ có generator riêng và thứ tự xử lý được thiết kế độc lập lịch scheduler, kết quả sẽ dễ tái lập hơn.

## 14. Checklist trước khi chốt thiết kế

1. **Mục đích:** Số dùng cho mô phỏng/kiểm thử hay một bí mật cần chống dự đoán?
2. **Thuật toán:** Chọn rõ `Random`, `SplittableRandom`, một `RandomGenerator` theo tên, `ThreadLocalRandom` hay `SecureRandom`.
3. **Seed:** Ai cung cấp? Có cố định để replay? Có liên quan dữ liệu bí mật không?
4. **Tính tái lập:** Cần cố định những lời gọi, bound, thứ tự, tác vụ và phiên bản nào?
5. **Kiểm thử:** Đang kiểm tra logic, dãy tái lập, phân bố thống kê hay biện pháp bảo mật?
6. **Đồng thời:** Có chia sẻ generator giữa nhiều luồng không; lịch xử lý có làm thay đổi vị trí lấy số không?
7. **Vận hành:** Thông tin nào được phép ghi log, và thông tin bí mật nào bắt buộc không lưu?

**Ghi nhớ:** Seed là công cụ **khởi tạo và tái lập trạng thái** của PRNG; lựa chọn thuật toán quyết định cách sinh chuỗi và các đặc tính cần đánh giá. Kiểm thử được bằng seed cố định **không có nghĩa** an toàn mật mã. Trong Java, hãy chọn `Random`/generator thích hợp cho mô phỏng có thể tái lập, và `SecureRandom` cho giá trị cần khó dự đoán, đồng thời kiểm thử đúng hành vi ứng dụng và kiểm soát bảo mật riêng.
