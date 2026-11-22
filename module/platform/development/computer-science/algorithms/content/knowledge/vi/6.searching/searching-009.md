# Tìm kiếm nhị phân trên giá trị đáp án

**Tìm kiếm nhị phân trên giá trị đáp án (binary search on the answer)** là kỹ thuật biến một bài toán **tối ưu** thành nhiều lần kiểm tra một câu hỏi **đúng/sai**: “Với giá trị ứng viên `x`, có tồn tại cách giải thỏa yêu cầu không?”. Nếu đáp án đúng/sai thay đổi theo **một chiều** khi `x` tăng, ta có thể dùng tìm kiếm nhị phân để xác định **ranh giới tối ưu**, thay vì thử lần lượt mọi giá trị.

Đây là một biến thể quan trọng của tìm kiếm nhị phân trong thuật toán. Ta không nhất thiết tìm phần tử trong một mảng đã sắp xếp; ta tìm giá trị của một tham số như **sức chứa tối thiểu**, **tốc độ tối thiểu**, **thời gian ít nhất** hoặc **độ dài lớn nhất** thỏa điều kiện. Điều kiện cốt lõi để áp dụng là **tính đơn điệu của hàm kiểm tra**, không phải việc dữ liệu đầu vào phải được sắp xếp.

## 1. Từ bài toán tối ưu sang phép kiểm tra khả thi

Giả sử bài toán hỏi: “Sức chứa nhỏ nhất của một con tàu để chuyển toàn bộ kiện hàng trong tối đa `D` ngày là bao nhiêu?”. Gọi `C` là sức chứa thử nghiệm và đặt:

```text
canShip(C) = true  nếu có thể chuyển hết hàng trong tối đa D ngày
           = false nếu không thể
```

Nếu có thể vận chuyển với sức chứa `C`, thì với sức chứa lớn hơn `C'` cũng có thể dùng đúng kế hoạch cũ. Vì vậy trạng thái của `canShip(C)` khi `C` tăng có dạng:

```text
C:          ...  4   5   6   7   8   9   ...
canShip(C): ...  F   F   T   T   T   T   ...
                       ^ ranh giới đầu tiên đúng: C = 6
```

Đây là bài toán tìm **giá trị nhỏ nhất thỏa điều kiện** (first true). Thay vì thử từng sức chứa, ta hỏi tại giá trị giữa miền, rồi loại bỏ một nửa các ứng viên.

Tương tự, bài toán “cắt những cuộn dây thành **ít nhất K đoạn**, độ dài mỗi đoạn lớn nhất là bao nhiêu?” thường cho hàm kiểm tra dạng **đúng rồi sai** khi tăng độ dài thử nghiệm. Ta cần tìm **giá trị lớn nhất còn đúng** (last true).

Hai dạng phải được phân biệt ngay từ đặc tả:

| Dạng | Trạng thái khi `x` tăng | Mục tiêu | Hành động khi kiểm tra đúng |
| --- | --- | --- | --- |
| **Minimize feasible** | `F F F T T T` | Tìm `x` nhỏ nhất có `P(x)=true` | Thu hẹp cận phải về `mid`. |
| **Maximize feasible** | `T T T F F F` | Tìm `x` lớn nhất có `P(x)=true` | Nâng cận trái lên `mid`. |

**Tính đơn điệu** nghĩa là một khi trạng thái đã chuyển thì không đổi ngược lại trong miền xét. Nếu kết quả là `F T F T`, tìm kiếm nhị phân theo ranh giới không có cơ sở đúng đắn.

## 2. Bốn bước thiết kế thuật toán

1. **Chọn giá trị cần tối ưu `x`:** xác định đơn vị, miền giá trị (số nguyên hay số thực), mục tiêu tối thiểu hay tối đa. Ví dụ `x` là sức chứa nguyên của tàu.
2. **Viết hàm `feasible(x)`:** chỉ cần trả `true/false`, nhưng phải chính xác với mọi `x` trong miền. Nhiều bài sử dụng **tham lam (greedy)**, mô phỏng một lịch xử lý hoặc thuật toán đồ thị để kiểm tra.
3. **Chứng minh tính đơn điệu:** giải thích tại sao nếu `x` khả thi thì các giá trị lớn hơn (hoặc nhỏ hơn) vẫn khả thi. Không chỉ dựa trên việc vài ví dụ có vẻ đơn điệu.
4. **Xác định cận và bất biến:** tìm miền chứa tối ưu, xử lý trường hợp vô nghiệm; chọn cách cập nhật cận khớp với dạng first true hoặc last true.

Với giá trị nguyên, mỗi phép kiểm tra giảm miền còn khoảng một nửa. Nếu ban đầu có `R` giá trị ứng viên và một lần `feasible` tốn `T(n)`, tổng chi phí thường là **O(T(n) · log R)**, cộng chi phí khởi tạo/các bước phụ. Không thể mặc định toàn bộ thuật toán chỉ O(log R) nếu phép kiểm tra còn phải duyệt `n` phần tử.

## 3. Mẫu tìm giá trị nhỏ nhất khả thi (first true)

Giả sử `P(x)` có dạng `false...false,true...true` trên miền nguyên `[low, high]`, và đã biết chắc `P(high)=true`. Mẫu giả mã:

```text
ALGORITHM MIN_FEASIBLE(low, high)
    REQUIRE low <= high
    REQUIRE P(high) = true
    // P đơn điệu: nếu P(x) đúng thì P(y) đúng với mọi y >= x.

    WHILE low < high DO
        mid <- low + FLOOR((high - low) / 2)

        IF P(mid) THEN
            high <- mid
        ELSE
            low <- mid + 1
        END IF
    END WHILE

    RETURN low
END ALGORITHM
```

**Vì sao đúng?**

- Trước và sau mỗi vòng, **vẫn tồn tại một ứng viên đúng trong `[low,high]`** (vì cận phải đã biết đúng và được cập nhật bằng một điểm đúng).
- Nếu `P(mid)` đúng, mọi giá trị lớn hơn `mid` không thể là câu trả lời **nhỏ hơn**, nên giữ lại `mid` và đoạn bên trái: `high = mid`.
- Nếu `P(mid)` sai, mọi giá trị nhỏ hơn hoặc bằng `mid` cũng sai vì đơn điệu, nên bỏ chúng: `low = mid + 1`.
- Khi `low == high`, miền chỉ còn một ứng viên và đó là giá trị khả thi nhỏ nhất.

Điểm giữa dùng **làm tròn xuống**. Khi `low < high`, `mid < high`, nên cập nhật `high = mid` hoặc `low = mid + 1` luôn thu nhỏ miền; không bị lặp vô hạn.

Công thức `low + (high - low)/2` trong Java giúp tránh rủi ro tràn khi cộng thẳng `low + high`, với điều kiện `high - low` biểu diễn được trong kiểu số đã chọn. Nếu miền có thể chạm cả hai cực trị kiểu số, cần xử lý tràn một cách riêng.

**Không tìm thấy đáp án:** mẫu trên chỉ đúng khi đã có cận phải khả thi. Nếu `P(high)` vẫn sai, không được tự trả `high` rồi coi là đáp án; phải tăng cận, đổi miền, hoặc trả trạng thái “vô nghiệm” theo đặc tả.

## 4. Ví dụ trọng tâm: sức chứa tàu nhỏ nhất để giao hàng đúng hạn

**Đề bài:** Có dãy kiện hàng nguyên dương `weights[0..n-1]`; tàu vận chuyển từng ngày theo **thứ tự đã cho**, không được tách một kiện hay thay đổi thứ tự. Mỗi ngày chở một nhóm liên tiếp có tổng khối lượng không vượt quá sức chứa `capacity`. Tìm sức chứa nguyên nhỏ nhất để chuyển hết hàng trong **tối đa `days` ngày**.

Tiền điều kiện: mảng không `null`, có ít nhất một kiện; mỗi khối lượng **dương**; `days ≥ 1`. Nếu cho phép dùng tối đa `days` ngày thì khi số ngày cho phép lớn hơn số kiện, sức chứa tối thiểu vẫn là khối lượng kiện nặng nhất.

### Chọn miền tìm kiếm

- **Cận dưới `low = max(weights)`:** tàu phải đủ sức chứa kiện lớn nhất vì không thể chia kiện.
- **Cận trên `high = sum(weights)`:** tàu có sức chứa tổng trọng lượng có thể chở tất cả trong một ngày, nên chắc chắn khả thi khi `days ≥ 1`.
- Với kiểu `int` cho từng kiện, nên tính tổng bằng `long` để tránh tràn khi số kiện nhiều.

Do vậy tối ưu luôn tồn tại trong `[max(weights),sum(weights)]` với các điều kiện đã nêu.

### Kiểm tra một sức chứa bằng tham lam

Với sức chứa thử `C`, đi theo thứ tự kiện hàng; mỗi ngày xếp **nhiều kiện liên tiếp nhất có thể** mà không vượt `C`, rồi chuyển sang ngày mới khi kiện tiếp theo không vừa.

```text
ALGORITHM CAN_SHIP(weights, days, C)
    IF any weight > C THEN
        RETURN false
    END IF

    usedDays <- 1
    currentLoad <- 0

    FOR EACH weight IN weights DO
        IF currentLoad + weight > C THEN
            usedDays <- usedDays + 1
            currentLoad <- weight
        ELSE
            currentLoad <- currentLoad + weight
        END IF
    END FOR

    RETURN usedDays <= days
END ALGORITHM
```

**Vì sao tham lam đúng?** Với sức chứa `C` và thứ tự kiện cố định, việc xếp tối đa số kiện đầu tiên vào ngày thứ nhất không thể khiến số ngày cần thiết nhiều hơn một kế hoạch để lại chỗ trống không cần thiết. Áp dụng lập luận tương tự cho phần hàng còn lại, ta thấy cách xếp tham lam dùng **số ngày ít nhất** với sức chứa `C`. Vì vậy, nếu cách tham lam cần nhiều hơn `days` ngày, không có cách chia nào khác theo đúng thứ tự có thể dùng ít ngày hơn.

Phép kiểm tra duyệt mỗi kiện đúng một lần: **O(n)** thời gian và **O(1)** bộ nhớ phụ. Khi tăng sức chứa, ta luôn có thể sử dụng lại lịch giao cũ, vì vậy `CAN_SHIP(C)` là một hàm **đơn điệu false → true**.

### Mô phỏng quá trình tìm kiếm

Lấy `weights = [3,2,2,4,1,4]`, `days = 3`. Cận ban đầu `low=4`, `high=16`.

| Lượt | `low` | `high` | `mid` | `CAN_SHIP(mid)` | Cập nhật |
| --- | ---: | ---: | ---: | --- | --- |
| 1 | 4 | 16 | 10 | Đúng: có thể chia ≤3 ngày. | `high=10` |
| 2 | 4 | 10 | 7 | Đúng: `[3,2,2]`, `[4,1]`, `[4]`. | `high=7` |
| 3 | 4 | 7 | 5 | Sai: cần 4 ngày. | `low=6` |
| 4 | 6 | 7 | 6 | Đúng: `[3,2]`, `[2,4]`, `[1,4]`. | `high=6` |

Hai cận gặp nhau ở `6`, nên sức chứa nhỏ nhất là **6**. Sức chứa `5` buộc phải chia thành `[3,2]`, `[2]`, `[4,1]`, `[4]`: bốn ngày. Chỉ kiểm tra rằng `6` khả thi chưa đủ; phải chứng minh `5` không khả thi và dựa vào tính đơn điệu để loại các giá trị nhỏ hơn.

## 5. Ví dụ khác: tốc độ xử lý tối thiểu

Cho `n` đống chuối, mỗi đống chứa số lượng nguyên dương `piles[i]`. Trong mỗi giờ chỉ xử lý một đống với tốc độ tối đa `k` quả/giờ; số quả còn lại của đống đó nếu ít hơn `k` sẽ được xử lý hết trong giờ, nhưng không chuyển sang đống khác trong cùng giờ. Hỏi tốc độ nguyên dương **nhỏ nhất** để hoàn thành trong tối đa `h` giờ.

Nếu mọi đống không rỗng và `h < n`, bài toán **vô nghiệm** theo mô hình này: mỗi đống cần ít nhất một giờ riêng. Khi `h ≥ n`, đáp án tồn tại trong `[1,max(piles)]`.

Với tốc độ `k`, số giờ bắt buộc dành cho đống `p` là **`ceil(p/k)`**. Phép kiểm tra chính xác là:

```text
CAN_FINISH(k) =
    (SUM over every pile p of CEIL(p / k)) <= h
```

Khi `k` tăng, số giờ không tăng, nên hàm kiểm tra cũng có dạng **false → true**. Đây vẫn là mẫu first true, chỉ khác cách xây dựng `feasible`.

Ví dụ `piles=[3,6,7,11]`, `h=8`:

- Tốc độ `k=3`: số giờ là `1+2+3+4=10`, không khả thi.
- Tốc độ `k=4`: số giờ là `1+2+2+3=8`, khả thi.
- Vì `k=3` sai và `k=4` đúng, tốc độ tối thiểu là **4**.

Trong Java, với `p ≥ 0` và `k > 0`, có thể tính `ceil(p/k)` bằng `(p + (long)k - 1)/k`. Ép sang `long` trước khi cộng giúp tránh tràn `int` khi `p` lớn. Tổng số giờ cũng cần dùng `long` để không tràn khi có nhiều đống.

## 6. Trường hợp đối ngẫu: tìm giá trị lớn nhất khả thi (last true)

Không phải bài tối ưu nào cũng là “nhỏ nhất mà đúng”. Ví dụ, có các cuộn dây dài nguyên dương `lengths[]`; được cắt thành các đoạn có cùng độ dài nguyên `L`, mỗi cuộn tạo ra `floor(lengths[i]/L)` đoạn. Mục tiêu là **độ dài lớn nhất `L ≥ 1`** sao cho tổng số đoạn cắt được **ít nhất `K`**.

Với `L` tăng, số đoạn cắt được chỉ có thể giảm hoặc giữ nguyên. Bởi vậy `CAN_CUT(L)` có dạng **true → false**. Ta tìm **last true**.

Nếu tổng độ dài toàn bộ cuộn **nhỏ hơn `K`**, thậm chí độ dài `L=1` cũng không đủ `K` đoạn, nên bài toán vô nghiệm (trong ví dụ Java quy ước trả `0`). Nếu `CAN_CUT(1)=true`, ta tìm trong `[1,max(lengths)]`.

```text
ALGORITHM MAX_FEASIBLE(low, high)
    REQUIRE low <= high
    REQUIRE P(low) = true
    // P đơn điệu: true...true,false...false.

    WHILE low < high DO
        mid <- low + CEIL((high - low) / 2)

        IF P(mid) THEN
            low <- mid
        ELSE
            high <- mid - 1
        END IF
    END WHILE

    RETURN low
END ALGORITHM
```

Ở đây điểm giữa phải **làm tròn lên**, vì nếu `low` và `high` chỉ cách một đơn vị, dùng điểm giữa làm tròn xuống sẽ cho `mid=low`; nhánh `P(mid)=true` cập nhật `low=mid` và lặp mãi. Với điểm giữa làm tròn lên, mỗi lượt chắc chắn thu nhỏ miền.

**Ví dụ:** `lengths=[9,7,5]`, `K=5`. Nếu `L=3`, ta nhận `3+2+1=6` đoạn, khả thi. Nếu `L=4`, chỉ `2+1+1=4` đoạn, không khả thi. Giá trị lớn nhất đúng là **`L=3`**. Không phải dùng hết độ dài của mỗi cuộn; phần dư có thể bị bỏ đi.

Số đoạn đếm được nên tích lũy bằng `long`, và có thể dừng sớm khi đạt `K`. Một lần kiểm tra mất O(n); miền tìm kiếm dài `M=max(lengths)` nên tổng chi phí **O(n log M)**.

## 7. Chương trình Java 17+ hoàn chỉnh

Tệp dưới đây chứa cả **first true** (sức chứa tàu, tốc độ xử lý) và **last true** (độ dài dây). Các hàm kiểm tra đầu vào theo đặc tả; kết quả tìm kiếm dùng `long` khi tổng số lượng có thể vượt `int`.

Tạo tệp **`AnswerBinarySearchDemo.java`**:

```java
public class AnswerBinarySearchDemo {

    public static long minShipCapacity(int[] weights, int maxDays) {
        if (weights == null || weights.length == 0 || maxDays < 1) {
            throw new IllegalArgumentException("Invalid shipping input");
        }

        long low = 0;
        long high = 0;
        for (int weight : weights) {
            if (weight <= 0) {
                throw new IllegalArgumentException("Weights must be positive");
            }
            low = Math.max(low, weight);
            high += weight;
        }

        while (low < high) {
            long mid = low + (high - low) / 2;
            if (canShip(weights, maxDays, mid)) {
                high = mid;
            } else {
                low = mid + 1;
            }
        }
        return low;
    }

    private static boolean canShip(int[] weights, int maxDays, long capacity) {
        int usedDays = 1;
        long load = 0;

        for (int weight : weights) {
            if (weight > capacity) {
                return false;
            }
            if (load + weight > capacity) {
                usedDays++;
                load = weight;
                if (usedDays > maxDays) {
                    return false;
                }
            } else {
                load += weight;
            }
        }
        return true;
    }

    public static int minEatingSpeed(int[] piles, int hours) {
        if (piles == null || piles.length == 0 || hours < piles.length) {
            throw new IllegalArgumentException("Invalid eating input");
        }

        int low = 1;
        int high = 0;
        for (int pile : piles) {
            if (pile <= 0) {
                throw new IllegalArgumentException("Piles must be positive");
            }
            high = Math.max(high, pile);
        }

        while (low < high) {
            int mid = low + (high - low) / 2;
            if (canFinish(piles, hours, mid)) {
                high = mid;
            } else {
                low = mid + 1;
            }
        }
        return low;
    }

    private static boolean canFinish(int[] piles, int hours, int speed) {
        long usedHours = 0;
        for (int pile : piles) {
            usedHours += (pile + (long) speed - 1) / speed;
            if (usedHours > hours) {
                return false;
            }
        }
        return true;
    }

    public static long maxRibbonLength(int[] lengths, long pieces) {
        if (lengths == null || lengths.length == 0 || pieces < 1) {
            throw new IllegalArgumentException("Invalid ribbon input");
        }

        long total = 0;
        long high = 0;
        for (int length : lengths) {
            if (length <= 0) {
                throw new IllegalArgumentException("Lengths must be positive");
            }
            total += length;
            high = Math.max(high, length);
        }

        if (total < pieces) {
            return 0; // Không thể cắt đủ số đoạn dài ít nhất 1.
        }

        long low = 1; // Đã chắc chắn khả thi.
        while (low < high) {
            long mid = low + (high - low + 1) / 2;
            if (canCut(lengths, pieces, mid)) {
                low = mid;
            } else {
                high = mid - 1;
            }
        }
        return low;
    }

    private static boolean canCut(int[] lengths, long pieces, long size) {
        long count = 0;
        for (int length : lengths) {
            count += length / size;
            if (count >= pieces) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) {
        int[] weights = {3, 2, 2, 4, 1, 4};
        System.out.println("ship3=" + minShipCapacity(weights, 3));
        System.out.println("ship1=" + minShipCapacity(weights, 1));
        System.out.println("ship6=" + minShipCapacity(weights, 6));
        System.out.println("ship10=" + minShipCapacity(
                new int[]{1,2,3,4,5,6,7,8,9,10}, 5));

        System.out.println("eat8=" + minEatingSpeed(
                new int[]{3,6,7,11}, 8));
        System.out.println("eat5=" + minEatingSpeed(
                new int[]{30,11,23,4,20}, 5));
        System.out.println("eat6=" + minEatingSpeed(
                new int[]{30,11,23,4,20}, 6));

        int[] ribbons = {9, 7, 5};
        System.out.println("ribbon5=" + maxRibbonLength(ribbons, 5));
        System.out.println("ribbon22=" + maxRibbonLength(ribbons, 22));
    }
}
```

Biên dịch và chạy:

```bash
javac AnswerBinarySearchDemo.java
java AnswerBinarySearchDemo
```

**Đầu ra chính xác:**

```text
ship3=6
ship1=16
ship6=4
ship10=15
eat8=4
eat5=30
eat6=23
ribbon5=3
ribbon22=0
```

Mọi hàm tìm tối ưu trong chương trình giữ nguyên mảng đầu vào; các hàm kiểm tra chỉ đọc dữ liệu. `maxRibbonLength` trả `0` khi không thể tạo đủ số đoạn dương, đây là **quy ước đầu ra riêng** của ví dụ; các đầu vào không hợp lệ như `pieces < 1` lại được báo bằng ngoại lệ.

Việc `canShip` và `canFinish` dừng sớm khi vượt giới hạn không làm sai kết quả: với sức chứa hoặc tốc độ thử đã cố định, lượng ngày/giờ đã sử dụng không thể tự giảm nhờ tiếp tục xử lý thêm kiện hàng hoặc đống chuối.

## 8. Bất biến, chứng minh đúng và điều kiện dừng

Một phép tìm kiếm nhị phân đúng cần hai tầng chứng minh:

**Tầng 1 — tính chính xác của `feasible(x)`:** hàm trả đúng/sai chính xác với ứng viên `x`. Ví dụ `canShip` dùng cách xếp tham lam đạt số ngày tối thiểu cho sức chứa đó; `canFinish` cộng đúng số giờ `ceil(p/k)`; `canCut` đếm đúng tổng số đoạn cắt được.

**Tầng 2 — tính đơn điệu và bất biến miền tìm kiếm:**

- Với bài **first true**, miền `[low,high]` luôn chứa **first true**, và `high` vẫn là ứng viên đúng; khi `P(mid)` đúng thì giữ `mid` bằng `high=mid`, còn khi sai thì bỏ `mid` bằng `low=mid+1`.
- Với bài **last true**, miền `[low,high]` luôn chứa **last true**, và `low` vẫn là ứng viên đúng; khi `P(mid)` đúng thì giữ `mid` bằng `low=mid`, còn khi sai thì bỏ `mid` bằng `high=mid-1`.

Cả hai dùng vòng `while (low < high)`, mỗi lượt làm **số lượng giá trị ứng viên giảm**. Mẫu first true chọn giữa làm tròn xuống; last true chọn giữa làm tròn lên để bảo đảm tiến triển.

Khi `low == high`, bất biến và tính đơn điệu chứng minh đó là ranh giới tối ưu. Đây là chứng minh về **tối ưu**, mạnh hơn việc chỉ kiểm tra đáp án trả về có khả thi.

## 9. Phân biệt tìm kiếm đáp án với tìm kiếm trên mảng sắp xếp

| Tiêu chí | Tìm kiếm nhị phân trong mảng sắp xếp | Tìm kiếm nhị phân trên đáp án |
| --- | --- | --- |
| Miền tìm kiếm | Chỉ số/phần tử của dãy sắp xếp. | Những giá trị có thể là đáp án, thường là số nguyên. |
| Điều kiện so sánh | So sánh khóa mục tiêu với phần tử tại giữa. | Gọi một hàm kiểm tra khả thi `P(mid)`. |
| Tính đơn điệu | Do thứ tự sắp xếp của mảng bảo đảm. | Phải **chứng minh** khi ứng viên tăng, khả thi chuyển theo một chiều. |
| Kết quả | Chỉ số, vị trí chèn hoặc trạng thái không tìm thấy. | Giá trị tối ưu nhỏ nhất/lớn nhất thỏa ràng buộc. |
| Chi phí | Thường O(log n) với truy cập ngẫu nhiên O(1). | O(T(n) log R) nếu một lần kiểm tra tốn T(n). |

Một số bài toán có thể giải bằng cả hai mô hình nếu tổ chức dữ liệu khác nhau, nhưng không nên áp dụng tìm kiếm nhị phân chỉ vì trong bài có số hoặc có từ “nhỏ nhất”. **Điều kiện đơn điệu của phép kiểm tra là căn cứ quyết định.**

## 10. Những sai lầm thường gặp

1. **Không chứng minh tính đơn điệu.** Ví dụ, nếu điều kiện khả thi đúng rồi lại sai rồi lại đúng khi tăng `x`, phép loại nửa miền không hợp lệ.
2. **Nhầm hướng tối ưu.** First true (`F→T`) phải giữ `mid` bên phải khi đúng; last true (`T→F`) phải giữ `mid` bên trái khi đúng.
3. **Chọn cận chưa được bảo đảm.** Với bài sức chứa, cận trên `sum(weights)` luôn đúng; với bài dây phải kiểm tra xem có đoạn dài ít nhất 1 nào đủ `K` không.
4. **Cập nhật cận gây vòng lặp vô hạn.** Ở last true, dùng điểm giữa làm tròn xuống và `low=mid` có thể giữ nguyên miền khi chỉ còn hai giá trị.
5. **Bỏ sót ứng viên biên.** Đặt `high=mid-1` khi `P(mid)` đúng trong bài first true có thể loại đúng đáp án.
6. **Viết hàm kiểm tra sai.** Ví dụ, với ship capacity, không được xếp lại thứ tự kiện hay chia một kiện thành hai ngày; với tốc độ xử lý, không được chuyển sang đống khác trong cùng một giờ.
7. **Không xử lý trường hợp vô nghiệm.** Khi miền không có giá trị khả thi, phải trả trạng thái phù hợp hoặc báo lỗi đầu vào, không coi một cận bất kỳ là đáp án.
8. **Tràn số.** `sum(weights)`, phép cộng giờ và `ceil(p/k)` cần kiểu đủ lớn; không dùng `(low+high)/2` nếu phép cộng có thể tràn.
9. **Quên phần chi phí kiểm tra.** Không thể báo thuật toán O(log R) khi mỗi lần kiểm tra phải duyệt cả mảng O(n).
10. **Sai ranh giới “tối đa” và “đúng bằng”.** Bài tàu ở đây cho phép **không quá** `days` ngày. Nếu đổi yêu cầu thành chính xác một số ngày và có ràng buộc về ngày rỗng, phải điều chỉnh đặc tả.

## 11. Checklist áp dụng cho bài mới

- **Ứng viên:** `x` biểu diễn điều gì, kiểu và đơn vị nào, cần tối thiểu hay tối đa?
- **Kiểm tra:** có thể viết `feasible(x)` đúng với mọi `x` không? Chi phí `T(n)` là bao nhiêu?
- **Đơn điệu:** giải thích được `F→T` hay `T→F` trên toàn miền không?
- **Cận:** `low`/`high` chứa tối ưu chưa? Một cận đã được biết khả thi chưa? Có trường hợp vô nghiệm không?
- **Cập nhật:** first true dùng điểm giữa xuống và `high=mid` khi đúng; last true dùng điểm giữa lên và `low=mid` khi đúng.
- **Biên và số học:** thử miền một phần tử, mọi giá trị khả thi, cận tối ưu sát đầu/cuối, dữ liệu lớn và phép tính có thể tràn.
- **Chứng minh:** kết hợp tính đúng của `feasible`, tính đơn điệu, bất biến miền và tính giảm của độ dài miền.

## 12. Bài tự luyện có lời giải

**Câu 1.** Với `weights=[3,2,2,4,1,4]`, `days=3`, vì sao không thể chọn sức chứa `5`? **Đáp án:** cách xếp tối đa theo thứ tự cần bốn nhóm `[3,2]`, `[2]`, `[4,1]`, `[4]`. Vì tham lam tối thiểu số ngày nên không có lịch nào dùng tối đa ba ngày với sức chứa này.

**Câu 2.** Nếu một bài có `P(x)` dạng `T T T F F`, ta tìm gì bằng binary search? **Đáp án:** có thể tìm vị trí **đúng cuối cùng** (last true), nghĩa là giá trị khả thi lớn nhất. Điểm giữa làm tròn lên giúp vòng lặp co lại khi cập nhật `low=mid`.

**Câu 3.** Vì sao thời gian của ship capacity là `O(n log R)`, với `R=sum(weights)-max(weights)+1`? **Đáp án:** mỗi lần kiểm tra dùng O(n) thao tác và tìm kiếm nhị phân cần O(log R) lần kiểm tra. Cần tính thêm O(n) để tìm tổng và giá trị lớn nhất.

**Câu 4.** Tốc độ `k=3` có đủ cho `piles=[3,6,7,11]`, `h=8` không? **Đáp án:** không; số giờ cần là `1+2+3+4=10`. Với `k=4`, số giờ là `1+2+2+3=8`, nên đáp án tối thiểu là 4.

**Câu 5.** Vì sao dây `[9,7,5]` không thể tạo ít nhất năm đoạn, mỗi đoạn dài 4? **Đáp án:** số đoạn tối đa là `floor(9/4)+floor(7/4)+floor(5/4)=2+1+1=4`. Độ dài 3 tạo được sáu đoạn nên tối ưu là 3.

**Câu 6.** Dùng `low=8`, `high=9` trong last true với `P(8)=true`, `P(9)=false`. Nếu `mid=floor((low+high)/2)`, điều gì xảy ra? **Đáp án:** `mid=8` và cập nhật `low=8` không đổi; vòng lặp có thể chạy mãi. Dùng điểm giữa làm tròn lên cho `mid=9`, sau đó `high=8` và kết thúc.

**Câu 7.** Nếu `P(x)` luôn sai trên miền `[1,100]`, có thể gọi trực tiếp mẫu first true trong mục 3 không? **Đáp án:** không, vì tiền điều kiện `P(high)=true` không được đáp ứng. Phải báo không có nghiệm trong miền hoặc mở rộng miền theo đặc tả.

**Câu 8.** Vì sao dữ liệu đầu vào của bài tàu không cần sắp xếp trước khi tìm kiếm? **Đáp án:** thuật toán tìm trên **sức chứa** chứ không tìm vị trí trong mảng. Hàm kiểm tra vẫn duyệt kiện theo đúng thứ tự đầu vào, và tính đơn điệu đến từ việc tăng sức chứa không làm một lịch khả thi trở thành bất khả thi.

**Ghi nhớ:** tìm kiếm nhị phân trên giá trị đáp án là kỹ thuật **tìm ranh giới của một điều kiện khả thi đơn điệu**. Muốn kết quả vừa nhanh vừa đúng, phải xây dựng đúng hàm kiểm tra, chứng minh đơn điệu, bảo đảm cận chứa tối ưu và cập nhật cận nhất quán với mục tiêu nhỏ nhất hay lớn nhất.
