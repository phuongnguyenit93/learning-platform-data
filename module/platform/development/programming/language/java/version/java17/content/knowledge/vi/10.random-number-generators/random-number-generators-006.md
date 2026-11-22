# Sinh số có giới hạn và kiểm tra miền giá trị trong Java 17

Khi sinh số giả ngẫu nhiên, chương trình thường cần một giá trị nằm trong một khoảng cụ thể: điểm từ 0 đến 100, số mặt xúc xắc từ 1 đến 6, số lượng phần tử từ 0 đến 9 hoặc một chỉ số hợp lệ của danh sách.

Trong Java, điều quan trọng là hiểu **cận dưới có được lấy hay không, cận trên có được lấy hay không**, kiểm tra miền đầu vào trước khi sinh và chọn đúng API theo mục đích. Java 17 cung cấp các cách sinh số có giới hạn qua \`Random\`, \`RandomGenerator\`, \`ThreadLocalRandom\` và \`SecureRandom\`.

> **Phạm vi:** Bài sử dụng API có sẵn trong Java 17. \`RandomGenerator\` thuộc package \`java.util.random\` được bổ sung từ Java 17. Không cần preview feature.

## 1. Khoảng giá trị: cận bao gồm và cận loại trừ

Trước khi gọi API, hãy xác định khoảng cần sinh.

Có hai cách biểu diễn thường gặp:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| \`[min, max]\` | Bao gồm cả cận dưới và cận trên | \`[1, 6]\` gồm 1, 2, 3, 4, 5, 6 |
| \`[min, max)\` | Bao gồm cận dưới, loại trừ cận trên | \`[1, 7)\` cũng gồm 1, 2, 3, 4, 5, 6 |

Nhiều API sinh số của Java dùng quy ước **cận dưới inclusive, cận trên exclusive**:

\`\`\`java
random.nextInt(origin, bound);
\`\`\`

Trong đó:

- \`origin\`: giá trị nhỏ nhất có thể xuất hiện.
- \`bound\`: giới hạn trên **không xuất hiện** trong kết quả.
- Điều kiện hợp lệ: \`origin < bound\`.

Ví dụ:

\`\`\`java
Random random = new Random();

int dice = random.nextInt(1, 7);
\`\`\`

Kết quả có thể là 1, 2, 3, 4, 5 hoặc 6. Giá trị 7 không thể được trả về.

**Mẹo nhớ:** Với API dạng \`nextInt(origin, bound)\`, muốn có khoảng nguyên từ 1 đến 6 thì truyền 1 và 7.

## 2. Các API sinh số có giới hạn trong Java 17

### 2.1. \`Random.nextInt(bound)\`: sinh từ 0 đến bound trừ 1

Đây là cách phổ biến để lấy số nguyên không âm có giới hạn:

\`\`\`java
import java.util.Random;

public class BoundedRandomDemo {
    public static void main(String[] args) {
        Random random = new Random();

        int value = random.nextInt(10);
        System.out.println(value);
    }
}
\`\`\`

Giá trị có thể là 0 đến 9.

Điều kiện:

- \`bound\` phải lớn hơn 0.
- Nếu \`bound <= 0\`, phương thức ném \`IllegalArgumentException\`.
- Kết quả không bao gồm \`bound\`.

Dùng để chọn chỉ số trong danh sách:

\`\`\`java
List<String> names = List.of("An", "Bình", "Chi");
Random random = new Random();

int index = random.nextInt(names.size());
String selected = names.get(index);
\`\`\`

Vì \`names.size()\` là 3 nên \`index\` chỉ có thể là 0, 1 hoặc 2, đúng với các chỉ số hợp lệ của danh sách.

Hãy kiểm tra danh sách rỗng trước khi gọi \`nextInt(names.size())\`, bởi \`nextInt(0)\` không hợp lệ.

### 2.2. \`Random.nextInt(origin, bound)\): sinh trong khoảng bất kỳ

Từ Java 17, \`Random\` triển khai interface \`RandomGenerator\`; phương thức \`nextInt(origin, bound)\` có thể dùng trực tiếp:

\`\`\`java
import java.util.Random;

public class RandomRangeDemo {
    public static void main(String[] args) {
        Random random = new Random();

        int temperature = random.nextInt(-10, 41);
        System.out.println(temperature);
    }
}
\`\`\`

Kết quả nằm trong khoảng \`[-10, 41)\`, tức là từ -10 đến 40.

Ví dụ khác:

\`\`\`java
int score = random.nextInt(0, 101);  // 0..100
int dice = random.nextInt(1, 7);     // 1..6
int offset = random.nextInt(-5, 6);  // -5..5
\`\`\`

Cận trên vẫn bị loại trừ. Với \`nextInt(origin, bound)\`, điều kiện \`origin >= bound\` sẽ làm phương thức ném \`IllegalArgumentException\`.

### 2.3. Dùng interface \`RandomGenerator\` trong Java 17

Java 17 bổ sung package \`java.util.random\` và interface \`RandomGenerator\` để cung cấp một giao diện chung cho các bộ sinh số giả ngẫu nhiên:

\`\`\`java
import java.util.Random;
import java.util.random.RandomGenerator;

public class RandomGeneratorDemo {
    public static void main(String[] args) {
        RandomGenerator generator = new Random(12345L);

        int dice = generator.nextInt(1, 7);
        long ticket = generator.nextLong(1L, 1_000_001L);
        double ratio = generator.nextDouble(0.0, 1.0);

        System.out.println(dice);
        System.out.println(ticket);
        System.out.println(ratio);
    }
}
\`\`\`

Interface này giúp code nhận một nguồn sinh số qua kiểu trừu tượng, thay vì phụ thuộc trực tiếp vào một lớp cụ thể. \`Random\` là một implementation có thể gán cho biến kiểu \`RandomGenerator\`.

Các phương thức có cận thường dùng:

| Phương thức | Khoảng kết quả |
|---|---|
| \`nextInt(bound)\` | \`[0, bound)\` |
| \`nextInt(origin, bound)\` | \`[origin, bound)\` |
| \`nextLong(bound)\` | \`[0, bound)\` |
| \`nextLong(origin, bound)\` | \`[origin, bound)\` |
| \`nextDouble(bound)\` | \`[0.0, bound)\` |
| \`nextDouble(origin, bound)\` | \`[origin, bound)\` |

Với các phương thức có hai cận, cận dưới phải nhỏ hơn cận trên. Với phương thức chỉ có \`bound\`, bound phải dương.

### 2.4. \`ThreadLocalRandom\` khi nhiều luồng cùng sinh số

Trong ứng dụng đa luồng, \`ThreadLocalRandom\` là lựa chọn tiện lợi để tránh nhiều luồng tranh chấp cùng một đối tượng \`Random\`:

\`\`\`java
import java.util.concurrent.ThreadLocalRandom;

public class ConcurrentRandomDemo {
    static int generateScore() {
        return ThreadLocalRandom.current().nextInt(0, 101);
    }
}
\`\`\`

Mỗi luồng sử dụng nguồn ngẫu nhiên riêng gắn với luồng hiện tại. Bạn không cần tự tạo một \`ThreadLocalRandom\` bằng constructor; hãy lấy instance qua \`ThreadLocalRandom.current()\`.

Dùng khi:

- Có nhiều luồng cần sinh số độc lập.
- Không cần tái tạo chuỗi kết quả bằng seed cố định cho từng luồng.
- Mục tiêu là hiệu năng và sự tiện dụng cho số giả ngẫu nhiên thông thường.

Không dùng \`ThreadLocalRandom\` để sinh token, mã xác thực hoặc dữ liệu cần chống đoán.

### 2.5. \`SecureRandom\` khi cần tính khó đoán

\`Random\` và \`ThreadLocalRandom\` phục vụ nhu cầu giả ngẫu nhiên thông thường. Nếu giá trị được dùng trong bối cảnh bảo mật, hãy chọn \`SecureRandom\`:

\`\`\`java
import java.security.SecureRandom;

public class SecureRandomDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();

        int verificationCode = secureRandom.nextInt(1_000_000);
        System.out.println(verificationCode);
    }
}
\`\`\`

Kết quả nằm trong khoảng 0 đến 999.999. Khi cần mã hiển thị đủ 6 chữ số, cần định dạng riêng vì giá trị số có thể bắt đầu bằng 0:

\`\`\`java
String code = "%06d".formatted(verificationCode);
System.out.println(code);
\`\`\`

Ví dụ \`verificationCode = 42\` sẽ được hiển thị thành \`000042\`.

\`SecureRandom\` phù hợp hơn cho token hoặc mã dùng trong quy trình bảo mật, nhưng vẫn cần thiết kế thêm thời hạn, số lần thử, lưu trữ và xác thực đúng cách. Sinh số an toàn không tự động làm toàn bộ quy trình xác thực an toàn.

**Không tự đặt seed dễ đoán cho \`SecureRandom\`** hoặc dùng \`new Random()\` để tạo token bảo mật.

## 3. Kiểm tra miền giá trị trước khi sinh số

Một yêu cầu thường gặp là người dùng nhập cận dưới và cận trên. Trước khi gọi API, chương trình phải xác định khoảng đó có hợp lệ theo yêu cầu nghiệp vụ hay không.

Ví dụ, muốn sinh điểm từ 0 đến 100:

- Cận dưới không được nhỏ hơn 0.
- Cận trên không được lớn hơn 100.
- Cận dưới không được lớn hơn cận trên.
- Nếu API dùng cận trên exclusive, khoảng cần có \`min < maxExclusive\`.

Tách riêng **kiểm tra miền nghiệp vụ** và **điều kiện của API sinh số** giúp tránh lỗi khó hiểu.

### 3.1. Kiểm tra khoảng half-open

\`\`\`java
static int randomInRange(RandomGenerator random, int min, int maxExclusive) {
    if (random == null) {
        throw new IllegalArgumentException("Nguồn random không được null");
    }

    if (min >= maxExclusive) {
        throw new IllegalArgumentException(
                "Cần min < maxExclusive");
    }

    return random.nextInt(min, maxExclusive);
}
\`\`\`

Phương thức trên yêu cầu khoảng có ít nhất một giá trị nguyên. Ví dụ:

| min | maxExclusive | Hợp lệ? | Kết quả có thể |
|---:|---:|---|---|
| 1 | 7 | Có | 1..6 |
| 0 | 1 | Có | Chỉ có 0 |
| -5 | 6 | Có | -5..5 |
| 5 | 5 | Không | Khoảng rỗng |
| 8 | 3 | Không | Cận dưới lớn hơn cận trên |

Có thể để API tự ném ngoại lệ khi cận không hợp lệ, nhưng tự kiểm tra trước thường giúp thông báo lỗi sát với hợp đồng nghiệp vụ hơn.

### 3.2. Kiểm tra miền điểm

Nếu hệ thống nhận khoảng điểm từ người dùng nhưng chỉ chấp nhận điểm từ 0 đến 100:

\`\`\`java
static int randomScore(
        RandomGenerator random,
        int min,
        int maxExclusive
) {
    if (min < 0 || maxExclusive > 101 || min >= maxExclusive) {
        throw new IllegalArgumentException(
                "Khoảng điểm phải nằm trong 0..100");
    }

    return random.nextInt(min, maxExclusive);
}
\`\`\`

Ví dụ:

- \`randomScore(random, 0, 101)\`: sinh 0..100.
- \`randomScore(random, 50, 81)\`: sinh 50..80.
- \`randomScore(random, -1, 50)\`: bị từ chối.
- \`randomScore(random, 50, 102)\`: bị từ chối.
- \`randomScore(random, 80, 50)\`: bị từ chối.

Ở đây \`maxExclusive <= 101\` vì giá trị 100 cần được bao gồm.

### 3.3. Phân biệt kiểm tra đầu vào với kiểm tra kết quả

Không nên chỉ sinh xong rồi mới kiểm tra xem kết quả có nằm trong miền hay không:

\`\`\`java
int value = random.nextInt();

// Không nên sinh trên toàn miền rồi lặp lại để lọc một khoảng đơn giản.
while (value < min || value >= maxExclusive) {
    value = random.nextInt();
}
\`\`\`

Cách này vừa khó đọc vừa có thể lặp rất lâu nếu khoảng hợp lệ nhỏ so với toàn miền. Khi API đã hỗ trợ cận, hãy truyền trực tiếp cận vào phương thức:

\`\`\`java
int value = random.nextInt(min, maxExclusive);
\`\`\`

Kiểm tra đầu vào trước để đảm bảo cận phù hợp với nghiệp vụ; để API sinh trực tiếp trong miền cần thiết.

## 4. Bao gồm cả cận trên: xử lý đúng off-by-one

Một nguồn lỗi phổ biến là yêu cầu khoảng **bao gồm cả hai đầu mút** nhưng lại truyền cận trên như thể nó inclusive.

Giả sử cần sinh số từ 1 đến 6:

\`\`\`java
int wrong = random.nextInt(1, 6);
\`\`\`

Đây là kết quả từ 1 đến 5; số 6 không thể xuất hiện.

Nếu cận trên nhỏ hơn \`Integer.MAX_VALUE\`, có thể viết:

\`\`\`java
int dice = random.nextInt(1, 6 + 1);
\`\`\`

Nhưng phép \`max + 1\` có thể **tràn số nguyên** nếu \`max == Integer.MAX_VALUE\`. Để xử lý toàn bộ miền \`int\` một cách an toàn, chuyển cận sang \`long\` trước khi cộng:

\`\`\`java
static int randomIntInclusive(
        RandomGenerator random,
        int minInclusive,
        int maxInclusive
) {
    if (random == null) {
        throw new IllegalArgumentException("Nguồn random không được null");
    }

    if (minInclusive > maxInclusive) {
        throw new IllegalArgumentException(
                "Cần minInclusive <= maxInclusive");
    }

    long exclusiveUpper = (long) maxInclusive + 1L;

    return (int) random.nextLong(
            (long) minInclusive,
            exclusiveUpper
    );
}
\`\`\`

Giải thích:

1. Ép \`maxInclusive\` sang \`long\` **trước khi cộng 1**.
2. Giá trị \`Integer.MAX_VALUE + 1\` vẫn biểu diễn được trong \`long\`.
3. \`nextLong(origin, bound)\` sinh trong khoảng half-open.
4. Mọi kết quả trong khoảng đều nằm trong miền \`int\`, nên có thể ép kiểu về \`int\` an toàn.

Hàm này xử lý được cả trường hợp \`minInclusive == maxInclusive\`: khoảng chỉ có một giá trị, và kết quả luôn là giá trị đó.

### 4.1. Không cộng 1 trong kiểu int trước khi ép kiểu

Sai:

\`\`\`java
int exclusiveUpper = maxInclusive + 1;
long bound = exclusiveUpper;
\`\`\`

Nếu \`maxInclusive\` là \`Integer.MAX_VALUE\`, phép cộng đã tràn trước khi gán vào \`long\`.

Đúng:

\`\`\`java
long exclusiveUpper = (long) maxInclusive + 1L;
\`\`\`

Nguyên tắc: **mở rộng kiểu dữ liệu trước phép toán có thể tràn**.

### 4.2. Khoảng inclusive cho long cần chú ý cận cực đại

Với \`long\`, phép \`maxInclusive + 1L\` có thể tràn nếu \`maxInclusive == Long.MAX_VALUE\`. Không áp dụng máy móc hàm trên cho toàn bộ miền \`long\`.

Nếu yêu cầu chỉ cần cận trên exclusive, dùng trực tiếp \`nextLong(origin, bound)\`. Nếu thật sự cần inclusive và có thể bao gồm \`Long.MAX_VALUE\`, phải thiết kế thuật toán xử lý trường hợp biên riêng, hoặc dùng một API/phương án chuyên biệt đã được kiểm chứng. Không âm thầm cộng 1 trong kiểu \`long\`.

## 5. Sinh số thực có giới hạn

Với \`double\`, có thể dùng \`nextDouble(origin, bound)\`:

\`\`\`java
RandomGenerator random = new Random();

double ratio = random.nextDouble(0.0, 1.0);
double temperature = random.nextDouble(18.5, 30.0);
\`\`\`

Khoảng có dạng \`[origin, bound)\`: cận dưới có thể xuất hiện, cận trên bị loại trừ. Điều kiện là \`origin < bound\`.

Không nhầm việc sinh \`double\` với việc sinh số thập phân chính xác:

- \`double\` biểu diễn số dấu phẩy động nhị phân, nhiều số thập phân không biểu diễn chính xác.
- \`nextDouble()\` phù hợp cho mô phỏng, xác suất, tỉ lệ hoặc thuật toán số.
- Không dùng \`double\` làm cách biểu diễn tiền tệ chính xác.
- Nếu nghiệp vụ cần số tiền hoặc số thập phân có scale cố định, hãy dùng \`BigDecimal\` và quy tắc làm tròn phù hợp.

Ví dụ tạo tỉ lệ giảm giá để minh họa:

\`\`\`java
double discountRate = random.nextDouble(0.05, 0.21);
\`\`\`

Giá trị nằm từ 0,05 đến nhỏ hơn 0,21. Nếu cần các mức rời rạc theo bước 0,01, có thể sinh số nguyên trong khoảng rồi chia theo quy tắc nghiệp vụ, thay vì so sánh \`double\` bằng phép bằng tuyệt đối.

## 6. Tránh cách sinh số sai bằng modulo

Một cách viết thường gặp nhưng không nên dùng:

\`\`\`java
int value = Math.abs(random.nextInt()) % 10;
\`\`\`

Có hai vấn đề:

1. \`Math.abs(Integer.MIN_VALUE)\` vẫn là số âm vì trị tuyệt đối của giá trị nhỏ nhất không biểu diễn được trong kiểu \`int\`.
2. Phép modulo trên kết quả ngẫu nhiên không đảm bảo mỗi số dư xuất hiện với xác suất bằng nhau khi số lượng giá trị nguồn không chia hết cho 10. Đây là **modulo bias**.

Cách đúng:

\`\`\`java
int value = random.nextInt(10);
\`\`\`

Hoặc với khoảng tùy chọn:

\`\`\`java
int value = random.nextInt(20, 31); // 20..30
\`\`\`

API bounded của Java xử lý việc lấy mẫu có giới hạn, không cần tự lấy modulo.

Tương tự, không nên viết:

\`\`\`java
int value = (random.nextInt() % 10 + 10) % 10;
\`\`\`

Biểu thức này có thể làm kết quả không âm nhưng **không loại bỏ modulo bias**.

## 7. Chọn bộ sinh số và seed phù hợp

### 7.1. \`Random\`: dễ dùng và có thể tái lập kết quả

\`\`\`java
Random random = new Random(12345L);

int first = random.nextInt(1, 7);
int second = random.nextInt(1, 7);
\`\`\`

Với cùng seed và cùng chuỗi lời gọi trên cùng thuật toán \`Random\`, kết quả có thể được tái lập. Điều này hữu ích cho:

- Bài tập và ví dụ giảng dạy.
- Test cần dữ liệu giả lập ổn định.
- Debug một lỗi phụ thuộc chuỗi số ngẫu nhiên.

Seed cố định khiến chuỗi kết quả có thể đoán được. **Không dùng seed cố định hoặc \`Random\` cho mục đích bảo mật.**

Nếu không truyền seed, \`Random\` tự khởi tạo trạng thái ban đầu. Điều đó không biến nó thành nguồn ngẫu nhiên mật mã.

### 7.2. \`ThreadLocalRandom\`: tác vụ thông thường trong môi trường đa luồng

\`\`\`java
int value = ThreadLocalRandom.current().nextInt(100, 201);
\`\`\`

Phù hợp khi nhiều luồng cần sinh số thông thường và không cần tự kiểm soát seed cho từng chuỗi kết quả.

### 7.3. \`SecureRandom\`: token và mã bảo mật

\`\`\`java
SecureRandom secureRandom = new SecureRandom();
byte[] tokenBytes = new byte[32];
secureRandom.nextBytes(tokenBytes);
\`\`\`

Dùng \`SecureRandom\` cho dữ liệu cần khó đoán, ví dụ token ngẫu nhiên. Nếu cần biểu diễn token thành chuỗi, dùng một encoding phù hợp như Base64 URL-safe; không dùng \`String.valueOf(byteArray)\` vì nó không biểu diễn nội dung byte theo cách mong muốn.

**Lưu ý:** Một mã OTP có sáu chữ số chỉ có một triệu khả năng. Ngoài việc dùng nguồn sinh an toàn, hệ thống phải có thời hạn hiệu lực, giới hạn số lần thử, chống phát lại và quy trình xác thực phù hợp.

### 7.4. Bảng lựa chọn nhanh

| Nhu cầu | Lựa chọn |
|---|---|
| Bài tập, mô phỏng đơn giản | \`Random\` |
| Test cần tái lập kết quả | \`new Random(seed)\` |
| Nhiều luồng sinh số thông thường | \`ThreadLocalRandom.current()\` |
| Cần một kiểu API chung cho nhiều implementation | \`RandomGenerator\` |
| Token, mã xác thực, giá trị khó đoán | \`SecureRandom\` |

Không có một bộ sinh số phù hợp cho mọi bài toán. Hãy chọn theo yêu cầu về khả năng tái lập, hiệu năng và bảo mật.

## 8. Sinh số từ danh sách và miền giá trị nghiệp vụ

### 8.1. Chọn một phần tử ngẫu nhiên trong danh sách

\`\`\`java
static <T> T chooseOne(
        List<T> values,
        RandomGenerator random
) {
    if (values == null || values.isEmpty()) {
        throw new IllegalArgumentException(
                "Danh sách phải có ít nhất một phần tử");
    }

    if (random == null) {
        throw new IllegalArgumentException("Nguồn random không được null");
    }

    return values.get(random.nextInt(values.size()));
}
\`\`\`

Chỉ số hợp lệ của danh sách có dạng \`[0, size)\`. Vì vậy \`nextInt(values.size())\` là phép chọn phù hợp. Nếu danh sách rỗng, \`size()\` bằng 0 và API không thể sinh chỉ số hợp lệ.

### 8.2. Sinh số lượng phần tử có giới hạn

Giả sử muốn sinh số lượng sản phẩm từ 1 đến 5:

\`\`\`java
int quantity = random.nextInt(1, 6);
\`\`\`

Nếu số lượng tối đa là một giá trị nhập vào, hãy xác thực trước:

\`\`\`java
static int randomQuantity(RandomGenerator random, int maxInclusive) {
    if (maxInclusive < 1) {
        throw new IllegalArgumentException(
                "Số lượng tối đa phải ít nhất là 1");
    }

    return random.nextInt(1, maxInclusive + 1);
}
\`\`\`

Đoạn này vẫn có nguy cơ tràn nếu \`maxInclusive == Integer.MAX_VALUE\`. Có thể dùng helper inclusive đã viết ở phần 4 để xử lý tổng quát hơn:

\`\`\`java
static int randomQuantity(
        RandomGenerator random,
        int maxInclusive
) {
    if (maxInclusive < 1) {
        throw new IllegalArgumentException(
                "Số lượng tối đa phải ít nhất là 1");
    }

    return randomIntInclusive(random, 1, maxInclusive);
}
\`\`\`

### 8.3. Kiểm tra miền nghiệp vụ trước khi tạo đối tượng

Giả sử điểm hợp lệ phải nằm từ 0 đến 100. Ta có thể mô hình hóa miền đó:

\`\`\`java
record Score(int value) {
    public Score {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "Điểm phải nằm trong 0..100");
        }
    }
}
\`\`\`

Sau đó sinh trực tiếp một giá trị hợp lệ:

\`\`\`java
Score score = new Score(random.nextInt(0, 101));
\`\`\`

Constructor kiểm tra miền dữ liệu cho mọi nguồn tạo đối tượng, kể cả dữ liệu đến từ API, file hoặc database. Bộ sinh số chỉ là một nguồn tạo dữ liệu; không nên đặt toàn bộ tính đúng đắn của miền nghiệp vụ vào chỗ gọi random.

## 9. Ví dụ hoàn chỉnh: sinh và kiểm tra miền điểm

Tạo file **\`BoundedScoreDemo.java\`**:

\`\`\`java
import java.util.Random;
import java.util.random.RandomGenerator;

public class BoundedScoreDemo {

    record Score(int value) {
        public Score {
            if (value < 0 || value > 100) {
                throw new IllegalArgumentException(
                        "Điểm phải nằm trong 0..100");
            }
        }
    }

    static int generateScore(
            RandomGenerator random,
            int minInclusive,
            int maxInclusive
    ) {
        if (minInclusive < 0
                || maxInclusive > 100
                || minInclusive > maxInclusive) {
            throw new IllegalArgumentException(
                    "Khoảng điểm phải nằm trong 0..100 và min <= max");
        }

        return randomIntInclusive(
                random,
                minInclusive,
                maxInclusive
        );
    }

    static int randomIntInclusive(
            RandomGenerator random,
            int minInclusive,
            int maxInclusive
    ) {
        if (random == null) {
            throw new IllegalArgumentException("Nguồn random không được null");
        }
        if (minInclusive > maxInclusive) {
            throw new IllegalArgumentException("min phải <= max");
        }

        return (int) random.nextLong(
                (long) minInclusive,
                (long) maxInclusive + 1L
        );
    }

    public static void main(String[] args) {
        RandomGenerator random = new Random(2026L);

        for (int i = 0; i < 5; i++) {
            int value = generateScore(random, 0, 100);
            Score score = new Score(value);
            System.out.println(score);
        }
    }
}
\`\`\`

Biên dịch và chạy với JDK 17:

\`\`\`bash
javac --release 17 BoundedScoreDemo.java
java BoundedScoreDemo
\`\`\`

Vì dùng seed cố định, chuỗi số được tái lập khi chạy lại cùng chương trình và cùng thứ tự gọi. Từng giá trị cụ thể không cần được ghi nhớ; điều cần quan tâm là:

- Giá trị luôn thuộc 0..100.
- \`generateScore\` từ chối khoảng nằm ngoài miền nghiệp vụ.
- \`Score\` tự bảo vệ bất biến của đối tượng.
- Helper inclusive dùng phép toán \`long\` để tránh lỗi \`max + 1\` trong kiểu \`int\`.

## 10. Các lỗi thường gặp

| Lỗi | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Dùng \`nextInt(1, 6)\` để gieo xúc xắc | Cận 6 bị loại trừ, chỉ sinh 1..5 | Dùng \`nextInt(1, 7)\` |
| Gọi \`nextInt(0)\` | Bound phải dương | Kiểm tra kích thước trước khi sinh |
| Gọi \`nextInt(min, max)\` khi \`min == max\` | Khoảng half-open rỗng | Xác định nghiệp vụ: nếu cần một giá trị duy nhất, dùng khoảng inclusive hoặc xử lý riêng |
| Cộng 1 vào \`Integer.MAX_VALUE\` bằng kiểu \`int\` | Tràn số | Ép sang \`long\` trước khi cộng |
| Dùng \`Math.abs(nextInt()) % n\` | Có trường hợp âm và phân phối modulo bị lệch | Dùng \`nextInt(n)\` |
| Nghĩ \`nextInt()\` luôn không âm | Không giới hạn trả số nguyên trong toàn miền, gồm số âm | Dùng overload có bound |
| Dùng \`Random\` tạo token bảo mật | Chuỗi giả ngẫu nhiên có thể dự đoán | Dùng \`SecureRandom\` |
| Sinh \`double\` cho tiền tệ | Sai số biểu diễn dấu phẩy động | Dùng \`BigDecimal\` và quy tắc tiền tệ |
| Chỉ kiểm tra kết quả sau khi sinh toàn miền | Có thể lặp lâu và khó đảm bảo hiệu năng | Kiểm tra cận rồi sinh trực tiếp trong miền |

## 11. Bài tập thực hành

### Bài 1: Sinh số trên xúc xắc

Viết phương thức \`rollDice(RandomGenerator random)\` trả về số nguyên từ 1 đến 6.

**Đáp án gợi ý:**

\`\`\`java
static int rollDice(RandomGenerator random) {
    return random.nextInt(1, 7);
}
\`\`\`

Cận trên 7 bị loại trừ, vì vậy 6 vẫn có thể xuất hiện.

### Bài 2: Tìm lỗi off-by-one

Đoạn mã:

\`\`\`java
int score = random.nextInt(0, 100);
\`\`\`

Yêu cầu là sinh điểm từ 0 đến 100, bao gồm cả 100. Đoạn mã sai ở đâu?

**Đáp án:** \`100\` bị loại trừ. Sửa thành:

\`\`\`java
int score = random.nextInt(0, 101);
\`\`\`

### Bài 3: Kiểm tra khoảng nhập vào

Viết hàm sinh số nguyên trong khoảng half-open \`[min, maxExclusive)\`; nếu \`min >= maxExclusive\`, ném \`IllegalArgumentException\`.

**Đáp án gợi ý:**

\`\`\`java
static int generate(
        RandomGenerator random,
        int min,
        int maxExclusive
) {
    if (min >= maxExclusive) {
        throw new IllegalArgumentException("Khoảng không hợp lệ");
    }

    return random.nextInt(min, maxExclusive);
}
\`\`\`

### Bài 4: Khoảng inclusive với cận lớn nhất

Vì sao không nên viết:

\`\`\`java
random.nextInt(min, maxInclusive + 1);
\`\`\`

khi \`maxInclusive\` có thể là \`Integer.MAX_VALUE\`?

**Đáp án:** Phép cộng xảy ra trong kiểu \`int\` và có thể tràn trước khi phương thức được gọi. Hãy chuyển sang \`long\` trước khi cộng, sau đó dùng \`nextLong((long) min, (long) maxInclusive + 1L)\` rồi ép kết quả về \`int\`.

### Bài 5: Chọn nguồn sinh số

Ghép tình huống với API phù hợp:

| Tình huống | Lựa chọn |
|---|---|
| Chạy test với chuỗi số lặp lại | \`new Random(seed)\` |
| Sinh số cho nhiều luồng xử lý | \`ThreadLocalRandom.current()\` |
| Sinh token khó đoán | \`SecureRandom\` |
| Viết API nhận nguồn random tổng quát trên Java 17 | \`RandomGenerator\` |

### Bài 6: Vì sao modulo không phù hợp?

Giải thích vì sao \`Math.abs(random.nextInt()) % 10\` không phải cách tốt để sinh số 0..9.

**Đáp án:** \`Math.abs(Integer.MIN_VALUE)\` vẫn âm, và modulo có thể tạo phân phối lệch nếu số lượng trạng thái nguồn không chia hết cho 10. Hãy dùng \`random.nextInt(10)\`.

## 12. Ghi nhớ

Khi sinh số có giới hạn trong Java 17, hãy xác định rõ khoảng trước:

~~~text
[min, max)  -> cận dưới có thể xuất hiện, cận trên không xuất hiện
[min, max]  -> cả hai cận đều có thể xuất hiện
~~~

Chọn API đúng với cách biểu diễn:

- \`nextInt(bound)\` cho khoảng \`[0, bound)\`.
- \`nextInt(origin, bound)\` cho khoảng \`[origin, bound)\`.
- \`nextLong(origin, bound)\` khi cần miền rộng hơn hoặc cần xử lý inclusive int bằng phép toán long.
- \`nextDouble(origin, bound)\` cho khoảng số thực.
- \`ThreadLocalRandom\` cho nhu cầu thông thường trong môi trường nhiều luồng.
- \`SecureRandom\` cho dữ liệu cần khó đoán.

Cuối cùng, **xác thực miền nghiệp vụ trước khi sinh**, tránh off-by-one và tràn số khi điều chỉnh cận, không tự dùng modulo để giới hạn kết quả và không dùng bộ sinh số thông thường cho mục đích bảo mật.

## 13. Tài liệu tham khảo

- [Oracle Java SE 17 — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): interface sinh số giả ngẫu nhiên, các phương thức có cận và quy tắc miền giá trị.
- [Oracle Java SE 17 — Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): bộ sinh số giả ngẫu nhiên truyền thống và khả năng tương thích với \`RandomGenerator\`.
- [Oracle Java SE 17 — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): sinh số gắn với luồng hiện tại.
- [Oracle Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): nguồn sinh số ngẫu nhiên dùng cho mục đích bảo mật.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): cải tiến và giao diện chung cho các bộ sinh số giả ngẫu nhiên từ Java 17.

