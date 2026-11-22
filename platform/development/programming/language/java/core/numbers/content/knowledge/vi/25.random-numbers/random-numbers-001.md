# Số giả ngẫu nhiên, seed và yêu cầu tái lập trong Java

## 1. PRNG có trạng thái: seed là điểm khởi đầu

**Pseudorandom number generator (PRNG)** tạo dãy trông ngẫu nhiên bằng một thuật toán xác định và trạng thái nội bộ. Seed (hạt giống) giúp khởi tạo trạng thái; sau mỗi lần sinh giá trị, trạng thái thường tiến tới vị trí mới:

```text
seed --> S0 --next--> r1,S1 --next--> r2,S2 --next--> r3,S3 ...
```

Ba mục tiêu **khác nhau** khi dùng nguồn ngẫu nhiên:

- **Exact replay:** phát lại đúng từng giá trị của một lần chạy.
- **Chất lượng thống kê:** dãy có phân phối/tương quan phù hợp mô phỏng.
- **Khó dự đoán:** kẻ quan sát không thể đoán được token, mã xác minh hoặc dữ liệu bí mật tiếp theo bằng cách tính toán khả thi.

Một bộ sinh cố định seed giúp test tái lập nhưng **không tự an toàn mật mã**. `java.util.Random` phục vụ mô phỏng thông thường; dữ liệu cần chống dự đoán sử dụng `java.security.SecureRandom` cùng quản lý token an toàn.

## 2. Vì sao cùng seed chưa chắc cùng kết quả nghiệp vụ?

```java
import java.util.Random;

Random first = new Random(42L);
Random second = new Random(42L);
int a = first.nextInt(100);   // 30
int b = first.nextInt(100);   // 63
int c = second.nextInt(100);  // 30
```

Hai đối tượng riêng có cùng seed cho cùng chuỗi **nếu cùng thuật toán, cùng lời gọi và thứ tự**. Đối tượng `first` đã ở vị trí thứ hai khi lấy `b`, trong khi `second` mới lấy số đầu tiên. Nếu thêm lần rút cho thời tiết trước phần thưởng trong trò chơi, số dành cho phần thưởng có thể thay đổi, dù seed vẫn bằng 42.

| Yếu tố khác nhau | Hệ quả |
| --- | --- |
| Thuật toán Random và SplittableRandom | Seed giống nhau không tạo thuật toán chung |
| Số lần/thứ tự gọi nextInt, nextLong, nextGaussian | Trạng thái có thể tiến số bước khác nhau |
| Bound/origin hay một nhánh điều kiện mới | Kết quả hoặc lịch sử tiêu thụ thay đổi |
| Các luồng dùng chung một generator | Thứ tự task nhận số phụ thuộc lịch scheduler |
| Input hoặc phiên bản mã thay đổi | Số lượt rút có thể không tương ứng |

Với `java.util.Random` cổ điển, thuật toán sử dụng trạng thái 48 bit và dãy kết quả với cùng seed/lịch gọi được đặc tả. Bài kế tiếp giải thích `Random.setSeed` và chi tiết 48 bit; các bài riêng bàn về generator theo thread, splitting và factory của Java 17.

## 3. Tái lập giống nhau hay tái lập về thống kê?

**Exact replay** yêu cầu các giá trị tại mỗi bước trùng nhau. Nó cần seed, tên thuật toán, lịch sử gọi và hoàn cảnh chạy được kiểm soát. Nếu một công việc đã đi nửa chặng, seed ban đầu **không** cho biết bộ sinh đang ở trạng thái nào; cần chạy lại cùng lịch sử hoặc lưu checkpoint khi có cách phù hợp.

**Statistical reproducibility** chỉ yêu cầu tính chất thống kê hoặc phân phối tương tự giữa các lần thử; không bắt buộc từng giá trị khớp nhau. Một seed cố định hữu ích cho regression test nhưng không chứng minh tính đúng của mô phỏng ở mọi seed, tính đều hay khả năng chống dự đoán.

Với mô phỏng song song, đừng dùng chung một đối tượng rồi mặc định mỗi task nhận cùng dãy giữa hai lần chạy: các thread có thể rút số theo thứ tự khác. Có thể dùng generator riêng theo **định danh task ổn định**, hoặc tách generator bằng `split()` theo lịch chia cố định. Những seed khác nhau không tự chứng minh các dãy độc lập thống kê; phải xét thuật toán và phương thức quản lý stream.

## 4. Ghi gì để tái hiện ca lỗi?

Với dữ liệu **không chứa bí mật**, hãy lưu tối thiểu:

1. **Tên lớp/thuật toán**, chẳng hạn `java.util.Random` hoặc `L64X128MixRandom` (Java 17).
2. **Seed thực tế** cùng cơ chế khởi tạo; nếu không ghi seed tự động, khó phát lại.
3. **Thứ tự lời gọi** như năm lần `nextInt(100)`, các bound/origin và số lần chia generator.
4. **Phiên bản mã và dữ liệu đầu vào** nếu chúng ảnh hưởng nhánh và lịch tiêu thụ.
5. **Cách phân công task→generator** cùng quy tắc chia seed khi workload chạy song song.

Không ghi seed/trạng thái CSPRNG hay token bảo mật nhằm mục đích replay như seed mô phỏng; loại thông tin này có thể chính là bí mật.

## 5. Ví dụ Java 17 chạy được

Lưu thành `RandomSeedReplayDemo.java`:

```java
import java.util.Arrays;
import java.util.Random;

public class RandomSeedReplayDemo {
    private static int[] samples(long seed, int count) {
        Random rng = new Random(seed);
        int[] values = new int[count];
        for (int i = 0; i < count; i++) {
            values[i] = rng.nextInt(100);
        }
        return values;
    }

    public static void main(String[] args) {
        int[] first = samples(42L, 5);
        int[] replay = samples(42L, 5);
        System.out.println(Arrays.toString(first));
        System.out.println("replay=" + Arrays.equals(first, replay));

        Random shifted = new Random(42L);
        shifted.nextInt(100);
        System.out.println("shiftedFirst=" + shifted.nextInt(100));
    }
}
```

```bash
javac --release 17 RandomSeedReplayDemo.java
java RandomSeedReplayDemo
```

```text
[30, 63, 48, 84, 70]
replay=true
shiftedFirst=63
```

Đây là kiểm tra khả năng tái lập dãy, không phải phép đo chất lượng thống kê hay kiểm chứng bảo mật.

## 6. Chọn API theo mục đích

| Nhu cầu | Hướng tiếp cận |
| --- | --- |
| Test/mô phỏng tuần tự cần phát lại | `new Random(seed)` và lịch gọi được kiểm soát |
| Đa luồng không cần seed tường minh | `ThreadLocalRandom.current()` trong worker |
| Cấp bộ sinh cho từng nhánh task | `SplittableRandom.split()` theo lịch chia rõ ràng |
| Cấu hình thuật toán Java 17 | `RandomGeneratorFactory.of(name).create(seed)` nếu thuật toán hỗ trợ seed |
| Sinh token/bí mật | `SecureRandom` và chính sách bảo vệ vòng đời dữ liệu |

**Ghi nhớ:** seed khởi tạo PRNG nhưng kết quả cuối phụ thuộc cả thuật toán, trình tự gọi và điều kiện xử lý. Tái lập và chống dự đoán là hai mục tiêu riêng, cần chọn đúng API.

**Tài liệu:** [Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html), [RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html), [SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html), [SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html).
