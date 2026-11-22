# Tìm vị trí xuất hiện đầu tiên và cuối cùng

Bài toán **tìm vị trí xuất hiện đầu tiên và cuối cùng** yêu cầu xác định vị trí nhỏ nhất và lớn nhất của một giá trị cần tìm (*target*) trong một dãy có thể chứa các giá trị trùng nhau. Nếu dãy không chứa target, ta thống nhất trả về **(-1, -1)**; nếu có đúng một lần, hai vị trí bằng nhau.

Hai tình huống phải phân biệt:

- **Dãy chưa sắp xếp:** các phần tử bằng target có thể nằm rải rác. Một lần **quét tuyến tính O(n)** tìm đúng vị trí đầu và cuối.
- **Dãy đã sắp xếp không giảm:** các phần tử bằng target nằm **liên tiếp**. Ta có thể dùng **tìm kiếm nhị phân hai biên**, gồm *lower bound* và *upper bound*, để tìm trong **O(log n)** thời gian và **O(1)** bộ nhớ phụ.

Các thuật toán dưới đây đánh chỉ số từ **0**, như mảng Java, và xác định **vị trí trong dãy đang tìm kiếm**. Nếu sắp xếp lại dãy chưa có thứ tự, vị trí trong dãy mới không còn là vị trí gốc.

## 1. Định nghĩa và ví dụ

Cho mảng `a` có `n` phần tử. Ta cần:

- `first = min {i | 0 <= i < n và a[i] == target}`.
- `last = max {i | 0 <= i < n và a[i] == target}`.
- Nếu không có chỉ số phù hợp: `first = last = -1`.

**Dãy chưa sắp xếp:**

```text
chỉ số:  0  1  2  3  4  5
a:      [5, 2, 5, 3, 5, 2]

target 5: first=0, last=4
target 2: first=1, last=5
target 7: first=-1, last=-1
```

Lưu ý rằng với target 5, các phần tử ở chỉ số 0, 2, 4 là 5 nhưng ở giữa còn có 2 và 3. Vì vậy **không** thể đếm số lần xuất hiện bằng `last - first + 1` ở dãy chưa sắp xếp.

**Dãy đã sắp xếp không giảm:**

```text
chỉ số:  0   1   2   3  4  5  6  7  8
a:      [-5, -2, -2, -2, 0, 0, 3, 7, 7]

target -2: first=1, last=3, có 3 lần
target  0: first=4, last=5, có 2 lần
target  4: first=-1, last=-1
target  7: first=7, last=8, có 2 lần
```

Vì các phần tử bằng nhau trong dãy có thứ tự tạo thành một đoạn liên tục, khi target tồn tại, **số lần xuất hiện bằng `last - first + 1`**.

## 2. Tìm đầu/cuối trong dãy chưa sắp xếp

Chỉ cần duyệt từ trái sang phải một lần:

1. Đặt `first=-1`, `last=-1`.
2. Với mỗi vị trí i, nếu `a[i] == target` thì:
   - Nếu first vẫn là -1, đặt first=i vì đây là lần gặp đầu tiên.
   - Luôn đặt last=i vì đó là lần gặp mới nhất tính đến thời điểm này.
3. Trả cặp kết quả sau khi xét hết mảng.

Đoạn phương thức Java minh họa (chương trình đầy đủ ở phần 7):

```java
static int[] findLinear(int[] a, int target) {
    int first = -1;
    int last = -1;
    for (int i = 0; i < a.length; i++) {
        if (a[i] == target) {
            if (first == -1) {
                first = i;
            }
            last = i;
        }
    }
    return new int[]{first, last};
}
```

**Chứng minh đúng bằng bất biến:** Sau khi xử lý tiền tố từ 0 đến i, nếu target chưa xuất hiện thì cả hai biến là -1. Nếu target đã xuất hiện, first là chỉ số nhỏ nhất trong tiền tố có giá trị bằng target và last là chỉ số lớn nhất như vậy. Phần tử mới chỉ có thể bổ sung một lần gặp ở **cuối tiền tố**, nên có thể cập nhật last, còn first được giữ kể từ lần gặp đầu tiên. Khi đã duyệt hết n phần tử, đó là chỉ số đầu/cuối của toàn mảng.

**Chi phí:** Có n lần kiểm tra, mỗi lần O(1), tổng thời gian **O(n)**, bộ nhớ phụ **O(1)**. Nếu chỉ hỏi vị trí đầu tiên, có thể dừng sau lần gặp đầu. Nhưng khi hỏi **vị trí cuối cùng**, ta phải tiếp tục kiểm tra về phía cuối vì có thể xuất hiện bản sao ở phần còn lại.

Một cách khác là quét từ trái để lấy first và từ phải để lấy last. Cách đó vẫn O(n), có thể dừng sớm trong một số dữ liệu, nhưng cách một lần quét tiện hơn khi cần cả hai kết quả.

## 3. Dãy đã sắp xếp: chuyển thành hai bài toán tìm biên

Đối với mảng sắp xếp **không giảm** (cho phép trùng nhau), thay vì tìm một chỉ số bất kỳ bằng target, ta tìm:

- **`lowerBound(a, target)`:** chỉ số **đầu tiên** mà `a[i] >= target`.
- **`upperBound(a, target)`:** chỉ số **đầu tiên** mà `a[i] > target`.

Nếu không có phần tử đáp ứng, cả hai hàm có thể trả **n** — vị trí sau cuối, **không phải chỉ số mảng hợp lệ**. Hai biên luôn nằm trong **[0,n]**.

Ví dụ với mảng `[-5,-2,-2,-2,0,0,3,7,7]` có n=9:

| Target | lowerBound | upperBound | Kết luận |
| --- | ---: | ---: | --- |
| -2 | 1 | 4 | Các lần xuất hiện ở 1, 2, 3 |
| 0 | 4 | 6 | Các lần xuất hiện ở 4, 5 |
| 4 | 7 | 7 | Không có 4; đây là vị trí chèn trước 7 |
| 7 | 7 | 9 | Các lần xuất hiện ở 7, 8 |
| 10 | 9 | 9 | Sau cuối mảng |
| -10 | 0 | 0 | Trước phần tử đầu tiên |

Nếu `lowerBound < upperBound` thì các chỉ số bằng target tạo thành đoạn **nửa mở `[lowerBound, upperBound)`**. Suy ra `first = lowerBound`, `last = upperBound - 1` và số lần xuất hiện `upperBound - lowerBound`. Với kết quả rỗng, hai biên bằng nhau; không được nhầm biên chèn với một lần xuất hiện thực tế.

### Tại sao hai biên đủ để tìm đầu/cuối?

Trong dãy tăng không giảm, mọi phần tử nhỏ hơn target đứng trước các phần tử bằng target, và mọi phần tử lớn hơn target đứng sau nhóm đó. Lower bound là ranh giới giữa “nhỏ hơn” và “không nhỏ hơn”; upper bound là ranh giới giữa “không lớn hơn” và “lớn hơn”. Phần giao giữa hai ranh giới chính là nhóm các phần tử **bằng target**.

## 4. Tìm lower bound bằng nhị phân

Dùng hai biến `left=0` và `right=n`, đại diện cho khoảng tìm kiếm **nửa mở [left, right)**.

```java
static int lowerBound(int[] a, int target) {
    int left = 0;
    int right = a.length;
    while (left < right) {
        int mid = left + (right - left) / 2;
        if (a[mid] < target) {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    return left;
}
```

Trong mỗi lượt:

- Nếu `a[mid] < target`, do mảng đã sắp xếp, mọi chỉ số không lớn hơn mid đều quá nhỏ. Loại cả mid bằng `left=mid+1`.
- Nếu `a[mid] >= target`, mid **có thể là biên đầu tiên**, vì vậy giữ mid và loại phần bên phải bằng `right=mid`.
- Khi left=right, khoảng tìm kiếm không còn phần tử; chính left là biên cần tìm.

**Bất biến vòng lặp:**

1. Các chỉ số `i < left` có `a[i] < target`.
2. Các chỉ số `i >= right` có `a[i] >= target`.
3. Biên đầu tiên có giá trị >= target nằm trong **đoạn biên ứng viên [left,right]**, kể cả trường hợp kết quả n.

Lúc khởi tạo, hai phần đã loại đều rỗng nên bất biến đúng. Hai nhánh cập nhật đều loại phần tử không thể là kết quả theo thứ tự mảng. Khi left=right, các vị trí phía trước đều nhỏ hơn target, còn các vị trí phía sau đều không nhỏ hơn target, nên left là vị trí đầu tiên đạt điều kiện.

**Chứng minh dừng:** Đại lượng `right-left` không âm, giảm nghiêm ngặt sau mỗi vòng vì khi `left<right` luôn có `left<=mid<right`. Nhánh trái làm left vượt qua mid; nhánh phải làm right bằng mid nhỏ hơn right cũ. Không thể giảm mãi trong tập số nguyên không âm.

Với target=-2, n=9:

```text
left right mid a[mid]  cập nhật
  0    9    4      0   right=4
  0    4    2     -2   right=2
  0    2    1     -2   right=1
  0    1    0     -5   left=1

lowerBound(-2) = 1
```

Chọn điều kiện đúng **`a[mid] < target`** là cốt lõi. Nếu đổi thành `<=`, ta sẽ bỏ cả các phần tử bằng target và tìm biên *sau* nhóm bằng nhau.

## 5. Tìm upper bound bằng nhị phân

Upper bound chỉ khác một điều kiện: tìm **phần tử đầu tiên lớn hơn target**.

```java
static int upperBound(int[] a, int target) {
    int left = 0;
    int right = a.length;
    while (left < right) {
        int mid = left + (right - left) / 2;
        if (a[mid] <= target) {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    return left;
}
```

Nếu `a[mid] <= target` thì mid và mọi phần tử trước nó không thể là phần tử đầu tiên **lớn hơn target**; đặt left=mid+1. Nếu `a[mid] > target`, giữ lại mid bằng right=mid.

Bất biến tương ứng là: mọi `i < left` thỏa `a[i] <= target`, mọi `i >= right` thỏa `a[i] > target`. Khi kết thúc, left là biên đầu tiên của nhóm giá trị lớn hơn target, hoặc n nếu không có.

Ví dụ target=-2:

```text
left=0, right=9, mid=4, a[mid]= 0: right=4
left=0, right=4, mid=2, a[mid]=-2: left=3
left=3, right=4, mid=3, a[mid]=-2: left=4
upperBound(-2) = 4
last = 4 - 1 = 3
```

### Kết hợp và xử lý trường hợp không tìm thấy

Với dãy tăng không giảm:

```java
int first = lowerBound(a, target);
if (first == a.length || a[first] != target) {
    return new IndexRange(-1, -1);
}
int afterLast = upperBound(a, target);
return new IndexRange(first, afterLast - 1);
```

Đoạn trên là **một phần của phương thức** trong chương trình đầy đủ phía dưới, không phải mã độc lập. Kiểm tra `first == a.length` **trước** `a[first]` rất quan trọng: Java đánh giá `||` theo cơ chế short-circuit; nếu first=n thì không truy cập mảng ở chỉ số n.

Để chỉ tìm **lần xuất hiện đầu**, dùng lower bound và xác nhận. Để chỉ tìm **lần xuất hiện cuối**, gọi upper bound rồi kiểm tra `p>0 && a[p-1]==target`; khi đúng last=p−1, còn không thì last=−1. Để chỉ **đếm số lần xuất hiện** trong dãy đã sắp xếp, tính upperBound − lowerBound, kết quả bằng 0 nếu target vắng mặt.

## 6. Tính đúng, kết thúc và độ phức tạp

**Tính đúng một phần:** Bất biến của lower bound đảm bảo kết quả là ranh giới đầu tiên có phần tử không nhỏ hơn target. Bất biến của upper bound đảm bảo kết quả là ranh giới đầu tiên có phần tử lớn hơn target. Tính chất đã sắp xếp khiến nhóm các phần tử bằng target nằm chính xác giữa hai ranh giới. Bước xác nhận phần tử tại lower bound bảo đảm không nhầm vị trí chèn thành lần xuất hiện.

**Kết thúc:** Mỗi vòng nhị phân rút ngắn đoạn ứng viên `right-left`. Sau hữu hạn lượt, left=right. Vì mỗi lượt tối thiểu giảm đoạn và thực tế thường loại khoảng một nửa, vòng lặp không thể vô hạn.

**Chi phí:** Một vòng nhị phân loại khoảng một nửa số chỉ số ứng viên, nên có O(log n) lượt với n≥1, mỗi lượt O(1). Hai vòng liên tiếp vẫn **O(log n) + O(log n) = O(log n)** thời gian; bộ nhớ phụ O(1) vì chỉ dùng vài biến nguyên. Nếu n=0, hai vòng đều chạy 0 lượt (O(1)); có thể viết chung là O(log(n+1)+1).

| Điều kiện dữ liệu và yêu cầu | Phương pháp | Thời gian/truy vấn | Bộ nhớ phụ |
| --- | --- | --- | --- |
| Chưa sắp xếp, cần first và last | Quét tuyến tính | O(n) | O(1) |
| Đã sắp xếp, chỉ cần first | lowerBound + xác nhận | O(log n) | O(1) |
| Đã sắp xếp, chỉ cần last | upperBound + xác nhận | O(log n) | O(1) |
| Đã sắp xếp, cần cả hai | lowerBound + upperBound | O(log n) | O(1) |
| Đã sắp xếp, chỉ cần số lần xuất hiện | upperBound − lowerBound | O(log n) | O(1) |

**Tiền điều kiện là thiết yếu:** Code tìm nhị phân **không kiểm tra mảng đã sắp xếp**. Nếu chạy bước xác thực thứ tự O(n) trước *mỗi* truy vấn thì tổng thời gian không còn O(log n). Trong ứng dụng thực tế, hãy đảm bảo dữ liệu có thứ tự từ trước, hoặc kiểm tra/sắp xếp **một lần** và tính chi phí đó riêng.

Nếu mảng chưa sắp xếp rồi ta **sắp xếp nó**, vị trí đầu/cuối trong mảng đã sắp xếp không phản ánh vị trí ban đầu. Nếu yêu cầu vị trí theo dãy gốc, hãy dùng quét tuyến tính hoặc lưu cặp *(giá trị, chỉ số gốc)* và chọn đúng các chỉ số gốc khi truy vấn.

## 7. Chương trình Java 17+ hoàn chỉnh

Chương trình sau dùng `record IndexRange` để trả một cặp chỉ số. `record` có sẵn ở Java 17, cung cấp cách hiển thị `IndexRange[first=..., last=...]`. Phiên bản nhị phân yêu cầu **mảng đã sắp xếp không giảm**, không dùng phép trừ hai giá trị để so sánh (tránh nguy cơ tràn số với Integer.MIN_VALUE/MAX_VALUE).

Lưu thành tệp **`FirstLastOccurrence.java`**:

```java
import java.util.Objects;

public class FirstLastOccurrence {
    record IndexRange(int first, int last) {}

    static IndexRange findLinear(int[] a, int target) {
        Objects.requireNonNull(a, "array must not be null");
        int first = -1;
        int last = -1;
        for (int i = 0; i < a.length; i++) {
            if (a[i] == target) {
                if (first == -1) {
                    first = i;
                }
                last = i;
            }
        }
        return new IndexRange(first, last);
    }

    // Yêu cầu a đã sắp xếp không giảm.
    static int lowerBound(int[] a, int target) {
        Objects.requireNonNull(a, "array must not be null");
        int left = 0;
        int right = a.length;
        while (left < right) {
            int mid = left + (right - left) / 2;
            if (a[mid] < target) {
                left = mid + 1;
            } else {
                right = mid;
            }
        }
        return left;
    }

    // Yêu cầu a đã sắp xếp không giảm.
    static int upperBound(int[] a, int target) {
        Objects.requireNonNull(a, "array must not be null");
        int left = 0;
        int right = a.length;
        while (left < right) {
            int mid = left + (right - left) / 2;
            if (a[mid] <= target) {
                left = mid + 1;
            } else {
                right = mid;
            }
        }
        return left;
    }

    static IndexRange findSorted(int[] a, int target) {
        Objects.requireNonNull(a, "array must not be null");
        int first = lowerBound(a, target);
        if (first == a.length || a[first] != target) {
            return new IndexRange(-1, -1);
        }
        int afterLast = upperBound(a, target);
        return new IndexRange(first, afterLast - 1);
    }

    static int countSorted(int[] a, int target) {
        Objects.requireNonNull(a, "array must not be null");
        return upperBound(a, target) - lowerBound(a, target);
    }

    public static void main(String[] args) {
        int[] unsorted = {5, 2, 5, 3, 5, 2};
        int[] sorted = {-5, -2, -2, -2, 0, 0, 3, 7, 7};

        System.out.println("unsorted 5: " + findLinear(unsorted, 5));
        System.out.println("unsorted 2: " + findLinear(unsorted, 2));
        System.out.println("unsorted 7: " + findLinear(unsorted, 7));

        System.out.println("sorted -2: " + findSorted(sorted, -2));
        System.out.println("sorted 0: " + findSorted(sorted, 0));
        System.out.println("sorted 4: " + findSorted(sorted, 4));
        System.out.println("sorted 7: " + findSorted(sorted, 7));
        System.out.println("count -2: " + countSorted(sorted, -2));
        System.out.println("lowerBound(4): " + lowerBound(sorted, 4));
        System.out.println("upperBound(4): " + upperBound(sorted, 4));

        System.out.println("empty: " + findSorted(new int[0], 2));
        System.out.println("all equal: "
                + findSorted(new int[]{5, 5, 5, 5}, 5));
        System.out.println("single hit: " + findSorted(new int[]{9}, 9));
        System.out.println("single miss: " + findSorted(new int[]{9}, 8));

        int[] extreme = {
            Integer.MIN_VALUE, Integer.MIN_VALUE, 0, Integer.MAX_VALUE
        };
        System.out.println("min int: "
                + findSorted(extreme, Integer.MIN_VALUE));
        System.out.println("max int: "
                + findSorted(extreme, Integer.MAX_VALUE));
    }
}
```

Biên dịch và chạy:

```bash
javac FirstLastOccurrence.java
java FirstLastOccurrence
```

Stdout chính xác:

```text
unsorted 5: IndexRange[first=0, last=4]
unsorted 2: IndexRange[first=1, last=5]
unsorted 7: IndexRange[first=-1, last=-1]
sorted -2: IndexRange[first=1, last=3]
sorted 0: IndexRange[first=4, last=5]
sorted 4: IndexRange[first=-1, last=-1]
sorted 7: IndexRange[first=7, last=8]
count -2: 3
lowerBound(4): 7
upperBound(4): 7
empty: IndexRange[first=-1, last=-1]
all equal: IndexRange[first=0, last=3]
single hit: IndexRange[first=0, last=0]
single miss: IndexRange[first=-1, last=-1]
min int: IndexRange[first=0, last=1]
max int: IndexRange[first=3, last=3]
```

**Giải thích:** Trong mảng chưa sắp xếp, số 5 xuất hiện ở 0,2,4 nên đầu=0, cuối=4. Trong mảng có thứ tự, -2 nằm ở 1,2,3, nên số lần xuất hiện bằng 3. Giá trị 4 không có, dù lowerBound và upperBound đều trả vị trí chèn 7. Mảng rỗng trả (-1,-1) không truy cập ngoài biên. Trường hợp tất cả phần tử bằng target có cặp (0,3); phần tử đơn lẻ có cặp (0,0). Các giá trị int cực trị được xử lý bằng so sánh trực tiếp, không trừ để so sánh.

## 8. Trường hợp biên và các bẫy logic

| Đầu vào | Kết quả mong đợi | Lý do |
| --- | --- | --- |
| Mảng rỗng, target bất kỳ | (-1, -1) | Không có phần tử nào |
| Mảng một phần tử bằng target | (0, 0) | Vừa đầu vừa cuối |
| Mảng một phần tử khác target | (-1, -1) | Không tìm thấy |
| Mọi phần tử bằng target | (0, n−1) khi n>0 | Nhóm bằng nhau chiếm cả dãy |
| Target nhỏ hơn mọi phần tử | (-1,-1) | Hai biên đều bằng 0 |
| Target lớn hơn mọi phần tử | (-1,-1) | Hai biên đều bằng n |
| Target nằm giữa hai giá trị khác nhau | (-1,-1) | Hai biên trùng nhau tại vị trí chèn |
| Target ở đầu hoặc cuối mảng | Biên 0 hoặc n−1 | Phải xử lý đúng phần tử biên |
| Mảng null | Chương trình minh họa ném NullPointerException | Kiểm tra tham số với Objects.requireNonNull |
| Dãy giảm dần, code đang viết cho tăng dần | Không có bảo đảm đúng | Cần đổi so sánh theo thứ tự thực tế |

**Lỗi số 1: trả ngay khi `a[mid] == target`.** Binary search thông thường có thể trả một lần xuất hiện bất kỳ; nó không tự bảo đảm là đầu hay cuối. Khi cần first, nếu gặp bằng nhau, phải tiếp tục dịch biên về bên trái; khi cần last, tiếp tục sang bên phải. Kỹ thuật lower/upper bound chuẩn hóa ý tưởng này.

**Lỗi số 2: nhầm `>=` với `>`.** lowerBound tìm đầu tiên `>= target`, còn upperBound tìm đầu tiên `> target`. Khác một dấu bằng nhưng khác hẳn kết quả trên nhóm phần tử trùng nhau.

**Lỗi số 3: nhầm vị trí chèn với vị trí xuất hiện.** Với mảng `[1,3,5]` và target=4, lowerBound=upperBound=2 nhưng `a[2]=5`. Vì vậy phải kiểm tra `a[first] == target` trước khi trả một cặp chỉ số.

**Lỗi số 4: tràn hoặc vượt chỉ số.** `(left+right)/2` có thể tràn int nếu tổng rất lớn; dùng `left+(right-left)/2`. Nếu lowerBound=n, `a[n]` không hợp lệ; kiểm tra `first==n` trước khi truy cập. Cũng không nên so sánh hai số int bằng cách lấy hiệu `a[mid]-target` vì hiệu có thể tràn.

**Lỗi số 5: vòng lặp không thu hẹp.** Với `while (left < right)`, nhánh loại mid về trái phải đặt `left=mid+1`, còn nhánh giữ mid phải đặt `right=mid`. Nếu đặt left=mid khi right=left+1, mid có thể vẫn bằng left và vòng lặp không tiến triển.

**Lỗi số 6: đổi mô hình đoạn chỉ số mà không đổi code.** Ở đây right ban đầu bằng n, dùng đoạn **[left,right)**. Nếu một phiên bản dùng `right=n-1` và `while(left<=right)`, đó là đoạn đóng; cần chứng minh và cập nhật khác. Không ghép tùy tiện nửa công thức của hai mô hình.

**Lỗi số 7: dùng nhị phân khi mảng chưa sắp xếp.** Quyết định bỏ nửa mảng dựa trên giả định có thứ tự. Với dãy chưa sắp xếp, phải dùng quét hoặc một cấu trúc tìm kiếm khác được duy trì đúng.

**Lỗi số 8: đếm bằng `last-first+1` trong dãy bất kỳ.** Công thức chỉ hợp lệ khi mọi phần tử giữa first và last đều bằng target, điều được bảo đảm bởi dãy đã sắp xếp theo cùng khóa so sánh.

**Lỗi số 9: không xác định chỉ số 0-based hay 1-based.** Ví dụ Java dùng 0-based. Nếu đề yêu cầu đánh số từ 1, chỉ chuyển các chỉ số hợp lệ bằng cách cộng 1; không chuyển -1 thành 0.

**Lỗi số 10: sắp xếp rồi khẳng định tìm được vị trí gốc.** Việc sắp xếp thay đổi vị trí các phần tử. Nếu cần trả vị trí đầu tiên/cuối cùng trong dãy ban đầu, phải quét ban đầu hoặc bảo toàn ánh xạ tới chỉ số gốc.

### Dãy giảm dần và kiểu dữ liệu khác

Với mảng sắp xếp **không tăng** (giảm dần cho phép trùng), cần đảo logic so sánh: biên trái của nhóm bằng target là phần tử đầu tiên `<= target`, còn biên sau cùng là phần tử đầu tiên `< target`. Không dùng trực tiếp hai hàm được viết cho dãy tăng.

Với danh sách đối tượng, có thể áp dụng ranh giới tương tự khi đã sắp xếp theo cùng một comparator và xác định “bằng target” theo cùng khóa. Với Java `String`, phải xác định đang tìm ký tự, chuỗi con, hay phần tử String trong danh sách: đó là các bài toán khác nhau. Nếu tìm vị trí ký tự trong chuỗi Java, chỉ số của `char` là đơn vị UTF-16, không đồng nhất với chỉ số Unicode code point trong mọi trường hợp.

**API Java:** `Arrays.binarySearch` có thể trả về **một** chỉ số tìm thấy khi có phần tử trùng nhưng không cam kết chọn first hoặc last. Muốn hai vị trí biên phải triển khai tiếp hoặc dùng API có cam kết rõ ràng về lower/upper bound.

## 9. Bài tập có lời giải

**Bài 1.** Cho mảng có thứ tự `[1,2,2,2,4,5,5]` và target=2. Tìm lowerBound, upperBound, first, last, số lần xuất hiện.

**Lời giải:** lowerBound=1, upperBound=4, first=1, last=3, số lần xuất hiện=3.

**Bài 2.** Vẫn mảng trên, target=3. Vì sao không thể trả first=4?

**Lời giải:** lowerBound=4, upperBound=4, nhưng a[4]=4 khác target=3. Vị trí 4 là vị trí chèn, nên kết quả phải (-1,-1).

**Bài 3.** Dãy chưa sắp xếp `[8,1,8,2,8,3]`, target=8. First và last là bao nhiêu? Có thể dùng last−first+1 để đếm không?

**Lời giải:** first=0, last=4, có ba vị trí bằng 8 là 0,2,4. Hiệu last−first+1=5 **không phải số lần xuất hiện** vì dãy không có thứ tự.

**Bài 4.** Với mảng có thứ tự `[4,4,4,4]`, target=4, xác định hai biên.

**Lời giải:** lowerBound=0, upperBound=4, first=0, last=3, count=4.

**Bài 5.** Chỉ cần tìm last bằng upperBound. Viết điều kiện xác nhận tồn tại.

**Lời giải:** Lấy p=upperBound(a,target); nếu `p>0 && a[p-1]==target` thì last=p-1, ngược lại last=-1. Nếu p=0 không được truy cập a[-1].

**Bài 6.** Hai lần nhị phân có làm thời gian tăng từ O(log n) thành O(n) không?

**Lời giải:** Không. Hai lần O(log n) cộng lại vẫn O(log n), chỉ tăng hằng số; mỗi lần đều thu hẹp khoảng tìm kiếm theo hệ số khoảng 2.

**Bài 7.** Nếu mảng có thứ tự `[-5,-2,-2,-2,0,0,3,7,7]`, kết quả lowerBound(10) và upperBound(-10) là bao nhiêu?

**Lời giải:** lowerBound(10)=9, vì mọi phần tử đều nhỏ hơn 10; upperBound(-10)=0, vì phần tử đầu đã lớn hơn -10.

**Bài 8.** Tại sao không nên tìm first bằng `Arrays.binarySearch` rồi mặc định kết quả là đầu tiên?

**Lời giải:** Với nhiều bản sao của target, binarySearch không có cam kết trả bản sao sớm nhất. Muốn kết quả chắc chắn đúng, cần tìm ranh giới đầu tiên bằng nhị phân hoặc quét theo yêu cầu.

## Ghi nhớ

- **Không sắp xếp:** quét tuyến tính để lấy first/last, thời gian O(n).
- **Đã sắp xếp không giảm:** lowerBound là chỉ số đầu tiên có giá trị **≥ target**, upperBound là chỉ số đầu tiên có giá trị **> target**.
- Nếu target tồn tại, **first=lowerBound, last=upperBound−1**, và số lần xuất hiện bằng **upperBound−lowerBound**. Nếu không có, trả **(-1,-1)**.
- Hai hàm biên trả số trong **[0,n]**; đừng truy cập `a[n]`. Xác nhận phần tử tồn tại trước khi trả vị trí.
- Chứng minh dựa vào **thứ tự mảng**, bất biến của hai vùng đã loại, và độ dài khoảng tìm kiếm giảm ở mỗi bước. Hai lần tìm nhị phân vẫn có thời gian **O(log n)**, bộ nhớ phụ **O(1)**.
