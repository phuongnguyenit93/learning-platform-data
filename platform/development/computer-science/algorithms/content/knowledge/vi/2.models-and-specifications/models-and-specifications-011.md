# Chọn ví dụ nhỏ, phản ví dụ và trường hợp biên

Khi thiết kế thuật toán, một ý tưởng có vẻ hợp lý chưa chắc đúng với mọi đầu vào. Ba công cụ tư duy đơn giản nhưng rất mạnh là **ví dụ nhỏ**, **phản ví dụ** và **trường hợp biên**. Chúng giúp hiểu đặc tả, làm rõ bất biến, phát hiện giả định sai và xây dựng bộ kiểm thử có chủ đích trước khi xử lý dữ liệu lớn.

Bài học thuộc chủ đề **Mô hình và đặc tả**: muốn chọn được ví dụ có ý nghĩa, trước hết phải hiểu **bài toán cho phép đầu vào nào**, **đầu ra đúng được xác định thế nào**, và **thuật toán dựa trên những điều kiện gì**. Không thể gọi một dữ liệu là “phản ví dụ” nếu chưa chỉ ra nó vi phạm một khẳng định cụ thể.

## 1. Ba khái niệm và vai trò khác nhau

### Ví dụ nhỏ (small example)
Là một đầu vào hợp lệ, đủ ít phần tử để người học có thể viết tay toàn bộ trạng thái và lần theo từng bước thuật toán. Ví dụ nhỏ dùng để **hiểu cơ chế**, xây dựng trực giác và nhận ra điều kiện cần duy trì. Kết quả đúng trên một vài ví dụ nhỏ chỉ là bằng chứng thử nghiệm, chưa phải chứng minh thuật toán đúng với mọi đầu vào.

### Phản ví dụ (counterexample)
Là một đầu vào **thỏa tất cả giả thiết của khẳng định** nhưng làm khẳng định đó sai. Chỉ cần **một phản ví dụ hợp lệ** là đủ bác bỏ một mệnh đề phổ quát kiểu “thuật toán này luôn tối ưu” hoặc “vòng lặp luôn trả vị trí đầu tiên”.

Ví dụ, để bác bỏ nhận định “luôn chọn đồng xu lớn nhất trước sẽ dùng ít đồng xu nhất với mọi hệ mệnh giá có đồng 1”, chọn mệnh giá {1, 3, 4} và số tiền 6:
- Tham lam lấy 4 + 1 + 1: **3 đồng**.
- Phương án 3 + 3: **2 đồng**.
- Mọi điều kiện đã nêu đều thỏa (mệnh giá dương và có đồng 1), nhưng kết quả tham lam không tối ưu. Vì vậy nhận định tổng quát sai.

Phản ví dụ **không** chứng minh rằng mọi phương pháp tham lam đều sai; nó chỉ bác bỏ khẳng định cụ thể trên miền đầu vào cụ thể.

### Trường hợp biên (edge/boundary case)
Là đầu vào ở sát hoặc đúng ngưỡng của miền hợp lệ: mảng rỗng nếu được phép, một phần tử, giá trị nhỏ nhất/lớn nhất, phần tử trùng, chỉ số đầu/cuối, số truy vấn bằng 0, khoảng độ dài 0, đồ thị chỉ có một đỉnh, v.v. Trường hợp biên thường làm lộ lỗi điều kiện dừng, sai khác giữa khoảng đóng và nửa mở, thiếu xử lý trạng thái rỗng, hoặc tràn số.

Một đầu vào có thể đồng thời là **ví dụ nhỏ**, **trường hợp biên** và **phản ví dụ** đối với một triển khai sai. Chẳng hạn mảng [5], truy vấn tìm vị trí chèn của 6 là trường hợp một phần tử, và cũng bác bỏ biến thể tìm kiếm nhị phân cài sai cận phải.

## 2. Đặc tả là điểm xuất phát

Trước khi tự chọn dữ liệu, hãy viết rõ:

1. **Miền đầu vào và tiền điều kiện (precondition):** loại dữ liệu, kích thước, giới hạn, quan hệ có sẵn như “mảng đã sắp xếp”.
2. **Kết quả phải trả về và hậu điều kiện (postcondition):** đầu ra đúng được xác định bằng mệnh đề nào?
3. **Các quy ước:** đánh chỉ số từ 0 hay 1, khoảng [l, r] hay [l, r), đồ thị có hướng hay vô hướng, có được trùng phần tử, giá trị thiếu được biểu diễn thế nào?
4. **Hành vi khi đầu vào ngoài miền:** bị từ chối, báo lỗi, hay không có cam kết? Trường hợp ngoài miền hợp lệ không tự động là phản ví dụ.

Ví dụ xuyên suốt bài: **lower_bound** trên mảng số nguyên được sắp xếp **không giảm**.

**Đầu vào:** mảng a có n phần tử, có thể rỗng; a[0] ≤ a[1] ≤ ... ≤ a[n−1]; một số nguyên x.

**Đầu ra:** chỉ số nhỏ nhất i trong [0, n) sao cho a[i] ≥ x; nếu không có thì trả n. Viết gọn:

~~~text
i = min({j | 0 <= j < n và a[j] >= x}) nếu tập không rỗng,
i = n nếu không tồn tại j như vậy.
~~~

Một hậu điều kiện dễ kiểm thử là:
- 0 ≤ i ≤ n.
- Mọi j < i đều có a[j] < x.
- Mọi j thỏa i ≤ j < n đều có a[j] ≥ x.

Ví dụ: a = [1, 2, 2, 4], x = 2 → i = 1. **Không** được trả 2 chỉ vì đó cũng là vị trí có giá trị 2: đặc tả yêu cầu **vị trí đầu tiên**. Với x = 5, đáp án đúng là 4 (bằng n); đó là một giá trị đầu ra hợp lệ, không phải truy cập vào a[4].

Phát biểu đúng đặc tả trước khi thử giúp tránh kiểm tra sai yêu cầu. Một hàm tìm “bất kỳ vị trí nào bằng x” khác lower_bound dù có thể trả kết quả giống nhau trên những dữ liệu không trùng.

## 3. Cách chọn ví dụ nhỏ thực sự có ích

Một ví dụ tốt không nhất thiết giống dữ liệu sản xuất. Nó nên **làm lộ quyết định chủ chốt** của thuật toán mà vẫn đủ nhỏ để theo dõi bằng tay.

### 3.1. Chọn số phần tử vừa đủ
- n = 0 hoặc n = 1 để xem khởi tạo, điều kiện dừng và giá trị mặc định.
- n = 2 hoặc n = 3 để tạo nhánh trái/phải, so sánh hoặc quyết định xung đột.
- n = 4 hoặc n = 5 khi cần quan sát hai lần lặp, hai lựa chọn tham lam, hoặc các phần tử trùng.

Ví dụ tìm kiếm nhị phân trên [1, 2, 2, 4] với x = 2 đủ để thấy vấn đề **giữ vị trí đầu tiên**; một mảng gồm hàng nghìn phần tử sẽ khó giải thích hơn nhưng không làm rõ thêm bản chất lỗi.

### 3.2. Thay đổi một yếu tố mỗi lần
Giữ thuật toán và phần lớn đầu vào cố định, lần lượt đổi:
- x từ nhỏ hơn mọi phần tử → bằng phần tử → nằm giữa hai giá trị → lớn hơn mọi phần tử.
- Mảng từ không trùng → có trùng → tất cả bằng nhau.
- Kích thước từ 0 → 1 → 2 → vài phần tử.

Cách thay đổi có kiểm soát giúp xác định vì sao hành vi khác đi. Nếu một phép thử đồng thời đổi kích thước, thứ tự, dấu của giá trị và số truy vấn, khi nó thất bại ta khó biết nguyên nhân.

### 3.3. Viết lại trạng thái trung gian
Với lower_bound, đặt l = 0, r = n và duy trì miền ứng viên **[l, r)**. Xét [1, 2, 2, 4], x = 2:

| Bước | l | r | mid | a[mid] | Quyết định |
| --- | ---: | ---: | ---: | ---: | --- |
| Ban đầu | 0 | 4 | – | – | Miền ứng viên [0, 4) |
| 1 | 0 | 4 | 2 | 2 | a[mid] ≥ x nên r = 2 |
| 2 | 0 | 2 | 1 | 2 | a[mid] ≥ x nên r = 1 |
| 3 | 0 | 1 | 0 | 1 | a[mid] < x nên l = 1 |
| Kết thúc | 1 | 1 | – | – | Trả 1 |

Ở mỗi bước, loại khỏi miền ứng viên những vị trí chắc chắn không thể là đáp án. Cách ghi trạng thái giúp kiểm tra lập luận bất biến, thay vì chỉ quan sát giá trị cuối.

## 4. Tạo phản ví dụ để thử một nhận định

Phương pháp hệ thống:

1. **Viết nhận định có thể kiểm chứng:** “chọn cục bộ tốt nhất luôn tối ưu”, “có thể bỏ phần tử trùng mà không ảnh hưởng kết quả”, “cập nhật cận phải theo cách này vẫn tìm phần tử đầu tiên”.
2. **Liệt kê các giả thiết phải giữ:** đầu vào đã sắp xếp? số không âm? được phép có trùng? khoảng có giao ở đầu mút không?
3. **Nhắm vào giả thiết ngầm:** thuật toán có đang dựa vào tính đơn điệu, tính trao đổi (exchange), hoặc bỏ qua phần tử trùng và thứ tự?
4. **Tạo cấu hình nhỏ làm các lựa chọn cạnh tranh:** thường 2–4 phần tử đã đủ để hai hướng giải quyết cho kết quả khác nhau.
5. **Tính kết quả đúng độc lập:** duyệt hết phương án nhỏ hoặc dùng một lời giải đơn giản đã rõ tính đúng; không lấy đầu ra của thuật toán đang nghi ngờ làm chuẩn.
6. **Thu nhỏ (shrink/minimize):** thử bỏ phần tử, giảm giá trị, giảm số bước mà lỗi vẫn xảy ra; giữ nguyên điều kiện đầu vào hợp lệ.
7. **Ghi nhận rõ điều bị bác bỏ:** đầu vào, đáp án chuẩn, đáp án của phương pháp sai và giả thiết bị vi phạm.

### 4.1. Phản ví dụ cho tham lam

Bài toán đổi 6 đơn vị với mệnh giá {1, 3, 4} như phần đầu. Thuật toán chọn đồng lớn nhất còn lấy được là hợp lệ, nhưng không đạt số đồng tối thiểu. Ý tưởng sai vì một lựa chọn lớn ở thời điểm hiện tại có thể ngăn cản hai lựa chọn nhỏ kết hợp tốt hơn.

Nếu ai khẳng định “chọn khoảng có thời điểm **bắt đầu sớm nhất** sẽ luôn chọn được nhiều khoảng không giao nhau nhất”, hãy xét các khoảng nửa mở:
- A = [1, 4)
- B = [2, 3)
- C = [3, 5)

Chọn bắt đầu sớm nhất lấy A, sau đó không thể lấy B hoặc C, được **1 khoảng**. Chọn B và C được **2 khoảng** vì [2, 3) và [3, 5) không giao nhau. Phản ví dụ này kiểm tra đúng giả thiết khoảng **nửa mở**. Nếu đề bài dùng khoảng đóng và coi tiếp xúc đầu mút là xung đột, phải kiểm tra lại tính hợp lệ của cặp B, C trước khi viện dẫn phản ví dụ.

Phản ví dụ cho một chiến lược **không đồng nghĩa** với lời giải thay thế đã được chứng minh. Sau khi bác bỏ quy tắc “bắt đầu sớm nhất”, muốn khẳng định quy tắc “kết thúc sớm nhất” là tối ưu vẫn phải chứng minh riêng bằng lập luận trao đổi.

### 4.2. Phản ví dụ cho điều kiện tìm kiếm nhị phân

Một cách viết tưởng hợp lý cho lower_bound lại dùng:

~~~text
nếu a[mid] <= x:
    l = mid + 1
ngược lại:
    r = mid
~~~

Điều kiện này tìm **vị trí đầu tiên có giá trị > x**, tức upper_bound, chứ không phải lower_bound. Mảng nhỏ a = [2, 2], x = 2:
- Kết quả đúng theo đặc tả lower_bound: **0**.
- Biến thể dùng ≤: **2**.

Phản ví dụ này hiệu quả hơn hàng trăm giá trị ngẫu nhiên không trùng vì nó nhắm thẳng vào ranh giới giữa **<** và **≤**.

Một lỗi khác là khởi tạo r = n − 1 rồi giữ nguyên thuật toán vốn được chứng minh trên khoảng nửa mở [l, r). Với a = [5], x = 6, điều kiện l < r sai ngay và trả 0, trong khi kết quả đúng là 1. Đây là sai quy ước biểu diễn miền ứng viên.

## 5. Chọn trường hợp biên theo đặc tả, không theo trực giác

“Biên” không chỉ là số lớn nhất. Hãy xét **ranh giới của miền hợp lệ**, **ranh giới phép so sánh** và **ranh giới trạng thái**.

| Nhóm tình huống | Dữ liệu mẫu cho lower_bound | Kết quả đúng | Lỗi thường lộ ra |
| --- | --- | ---: | --- |
| Rỗng, nếu cho phép | a = [], x = 7 | 0 | Đọc a[0], chia hoặc lấy mid không hợp lệ |
| Một phần tử, bằng x | a = [5], x = 5 | 0 | Dùng ≤ thay cho < |
| Một phần tử, lớn hơn x | a = [5], x = 4 | 0 | Sai nhánh tìm kiếm |
| Một phần tử, nhỏ hơn x | a = [5], x = 6 | 1 | Khởi tạo r = n − 1 |
| Giá trị lặp | a = [2, 2], x = 2 | 0 | Trả vị trí tùy ý thay vì đầu tiên |
| Tất cả bằng nhau | a = [3, 3, 3], x = 3 | 0 | Không xử lý đoạn trùng |
| x nhỏ hơn mọi giá trị | a = [2, 4], x = 1 | 0 | Không tìm được chèn đầu |
| x nằm giữa hai giá trị | a = [1, 4], x = 3 | 1 | Nhầm tìm giá trị bằng x với vị trí chèn |
| x lớn hơn mọi giá trị | a = [2, 4], x = 7 | 2 | Trả n − 1 thay vì n |
| Có số âm | a = [-3, -1, 2], x = -2 | 1 | Giả định sai rằng mọi giá trị ≥ 0 |

Các giá trị âm trong hàng cuối không đặc biệt về kỹ thuật tìm kiếm, nhưng giúp phát hiện những cài đặt vô tình giả định dữ liệu chỉ có số dương. Mảng **chưa sắp xếp** không phải trường hợp biên hợp lệ của đặc tả trên; nó vi phạm tiền điều kiện nên phải kiểm tra ở một nhánh kiểm thử xác thực đầu vào, nếu API có quy định xử lý đầu vào sai.

### Các loại biên cần nghĩ tới ở bài toán khác

- **Kích thước:** 0, 1, 2, lớn nhất theo giới hạn; độ dài bằng đúng giới hạn và ngay sát giới hạn.
- **Giá trị:** 0, ±1, âm, cực trị, chênh lệch rất lớn, tổng gần ngưỡng tràn int hoặc long.
- **Quan hệ:** hai phần tử bằng nhau, tất cả bằng nhau, đã sắp xếp/tăng/giảm, các khoảng vừa chạm nhau, hai đỉnh trùng, không có cạnh, nhiều cạnh song song nếu được phép.
- **Cấu trúc:** cây chỉ một nút, cây lệch như danh sách, đồ thị không liên thông, chu trình, đỉnh cô lập, nhiều thành phần liên thông.
- **Thao tác:** không có truy vấn, một truy vấn, cập nhật đầu/cuối, xóa phần tử duy nhất, truy vấn lặp lại, cập nhật rồi truy vấn cùng vị trí.
- **Chỉ số:** đầu 0, cuối n − 1, vị trí chèn n; khoảng [l, r) với l = r (rỗng), l = 0, r = n. Với n = 0, chỉ số n − 1 không hợp lệ.
- **Ràng buộc đặc biệt:** nếu bài đảm bảo n ≥ 1, không lấy n = 0 làm phản ví dụ của thuật toán chỉ cần đúng trên miền n ≥ 1. Nếu bài cấm giá trị âm, một mẫu âm cũng không bác bỏ thuật toán.

Đối với số nguyên trong Java, chú ý **tràn số ở phép tính trung gian**. Ví dụ muốn tính trung điểm của đoạn chỉ số, dùng l + (r − l) / 2 thay cho (l + r) / 2 khi l + r có nguy cơ vượt giới hạn int; với miền l, r không âm và 0 ≤ l ≤ r ≤ n, công thức đầu giữ kết quả trong miền.

## 6. Chọn chuẩn đối chiếu (oracle) độc lập

Một ví dụ chỉ giúp kiểm tra nếu biết **đầu ra kỳ vọng** từ một nguồn đáng tin hơn cách cài đặt đang được kiểm tra. Có nhiều cách tạo oracle:

**Tính bằng định nghĩa.** Với lower_bound, quét từ trái sang phải đến phần tử đầu tiên ≥ x; nếu hết mảng thì trả n. Mất O(n) nhưng đơn giản và dễ đối chiếu với tìm kiếm nhị phân O(log n).

**Duyệt hết phương án với dữ liệu nhỏ.** Với bài chọn tập con, phân hoạch, xếp lịch hoặc đổi tiền, có thể thử các phương án hợp lệ khi n nhỏ rồi chọn kết quả tốt nhất. Tốc độ chậm không thành vấn đề ở dữ liệu nhỏ; tránh phụ thuộc vào cùng một suy luận tham lam đang bị nghi ngờ.

**Kiểm tra tính chất cần luôn đúng.** Với lower_bound, ngoài so sánh với oracle, kiểm tra i thuộc [0, n], các phần tử trước i đều < x và từ i trở đi đều ≥ x. Với kết quả đường đi, kiểm tra đường đi nối tiếp đúng đỉnh và tổng trọng số phù hợp; với kết quả sắp xếp, kiểm tra không giảm **và** giữ nguyên đa tập phần tử.

**Biến đổi bảo toàn quan hệ (metamorphic testing).** Khi không biết sẵn đáp án đầy đủ, có thể dùng quan hệ giữa các đầu vào: cộng cùng một hằng số vào mọi phần tử và x (nếu không tràn số) không đổi vị trí lower_bound; thêm phần tử lớn hơn mọi phần tử hiện có không làm đổi kết quả truy vấn x nhỏ hơn hoặc bằng phần tử lớn nhất cũ. Những quan hệ này bổ sung kiểm thử nhưng cũng phải được chứng minh từ đặc tả.

**Hai triển khai độc lập (differential testing).** So sánh lời giải tối ưu với lời giải đơn giản. Nếu cả hai chia sẻ cùng lỗi thiết kế, kết quả khớp vẫn có thể sai; vì thế nên bổ sung bất biến và ví dụ suy ra bằng tay.

## 7. Chương trình Java 17: ví dụ biên và kiểm thử vét cạn nhỏ

Chương trình sau triển khai lower_bound đúng trên mảng sắp xếp không giảm và một oracle quét tuyến tính. Nó in ba ví dụ nhỏ, sau đó sinh **toàn bộ mảng không giảm** có độ dài từ 0 đến 4 với giá trị trong {-1, 0, 1}. Với mỗi mảng, chương trình kiểm tra 5 giá trị x từ -2 đến 2.

~~~java
import java.util.Arrays;

public class SmallCaseCounterexampleDemo {
    private static long checked = 0;

    static int lowerBound(int[] a, int x) {
        int left = 0;
        int right = a.length; // Miền ứng viên [left, right)

        while (left < right) {
            int mid = left + (right - left) / 2;
            if (a[mid] < x) {
                left = mid + 1;
            } else {
                right = mid;
            }
        }
        return left;
    }

    static int linearReference(int[] a, int x) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] >= x) {
                return i;
            }
        }
        return a.length;
    }

    static void checkAllTargets(int[] a) {
        for (int x = -2; x <= 2; x++) {
            int expected = linearReference(a, x);
            int actual = lowerBound(a, x);
            if (expected != actual) {
                throw new AssertionError(
                    "a=" + Arrays.toString(a)
                    + ", x=" + x
                    + ", expected=" + expected
                    + ", actual=" + actual
                );
            }
            checked++;
        }
    }

    // Các chữ số 0, 1, 2 được đổi thành các giá trị -1, 0, 1.
    // Bắt đầu mỗi vị trí bằng chữ số của vị trí trước -> không giảm.
    static void enumerateSorted(int[] a, int index, int minDigit) {
        if (index == a.length) {
            checkAllTargets(a);
            return;
        }
        for (int digit = minDigit; digit <= 2; digit++) {
            a[index] = digit - 1;
            enumerateSorted(a, index + 1, digit);
        }
    }

    public static void main(String[] args) {
        System.out.println("case1=" + lowerBound(new int[]{1, 2, 2, 4}, 2));
        System.out.println("case2=" + lowerBound(new int[]{2, 2}, 2));
        System.out.println("case3=" + lowerBound(new int[]{}, 7));

        for (int n = 0; n <= 4; n++) {
            enumerateSorted(new int[n], 0, 0);
        }
        System.out.println("checked=" + checked);
    }
}
~~~

Lưu thành **SmallCaseCounterexampleDemo.java** rồi chạy:

~~~bash
javac SmallCaseCounterexampleDemo.java
java SmallCaseCounterexampleDemo
~~~

**Đầu ra chính xác:**

~~~text
case1=1
case2=0
case3=0
checked=175
~~~

**Giải thích con số 175.** Có C(n + 2, 2) mảng không giảm độ dài n trên 3 giá trị {-1, 0, 1}, với n = 0, 1, 2, 3, 4 lần lượt là 1, 3, 6, 10, 15 mảng. Tổng cộng **35 mảng**, mỗi mảng kiểm tra **5 giá trị x**, nên có 35 × 5 = **175 phép đối chiếu**. Mảng rỗng vẫn được sinh và kiểm tra đúng 5 lần.

**Tại sao triển khai hoạt động?** Trong lowerBound, bất biến quan trọng là không có vị trí nào đứng trước left có thể là lời giải (các vị trí đó chứa giá trị < x), và mọi vị trí từ right trở đi đều thỏa giá trị ≥ x nếu còn nằm trong mảng. Mỗi vòng lặp loại ít nhất một vị trí khỏi miền ứng viên [left, right), nên vòng lặp kết thúc. Khi left = right, vị trí này là ranh giới đầu tiên giữa các phần tử < x và ≥ x (hoặc n nếu không có phần tử ≥ x).

**Giới hạn của kiểm thử:** 175 trường hợp chỉ bao phủ các mảng rất nhỏ trên ba giá trị và năm truy vấn. Kiểm thử vét cạn trên miền hữu hạn đó **không chứng minh** đúng cho mọi kích thước, mọi giá trị int hoặc mọi môi trường. Lập luận bất biến và tính kết thúc mới hỗ trợ chứng minh tổng quát. Nếu thay đổi dòng if thành a[mid] <= x, phép đối chiếu với oracle sẽ thất bại trên những mảng có phần tử bằng x.

## 8. Quy trình thực hành khi đề xuất hoặc sửa thuật toán

Một quy trình ngắn, có thể áp dụng trước khi viết lời giải hoàn chỉnh:

1. **Chép lại đặc tả bằng lời và ký hiệu.** Xác định rõ miền đầu vào, quy ước và hậu điều kiện; phân biệt đầu vào hợp lệ với đầu vào sai.
2. **Chọn ví dụ bình thường nhỏ nhất đủ thấy cơ chế.** Tự tính đáp án trước khi chạy thuật toán; đi từng bước và ghi trạng thái quan trọng.
3. **Xác định “chỗ dễ sai nhất”.** Điều kiện < hay ≤, thứ tự hay đa tập, trường hợp không tồn tại, hai lựa chọn cục bộ cạnh tranh, chu trình, giá trị âm/tràn số?
4. **Chọn các biên sát điều kiện đó.** Thử kích thước 0/1/2, giá trị đúng bằng ngưỡng, vừa thấp hơn/vừa cao hơn, trùng, đầu/cuối, n khi không tìm thấy.
5. **Tìm phản ví dụ đối với giả thuyết đáng ngờ.** Duyệt hết cấu hình nhỏ hoặc tạo mẫu đối kháng, rồi thu nhỏ mẫu làm sai đến mức dễ hiểu.
6. **Dùng oracle độc lập.** So sánh với quét tuyến tính, vét cạn hoặc một đặc tả thực thi đơn giản; thêm kiểm tra bất biến và các quan hệ biến đổi.
7. **Sửa nguyên nhân, không chỉ vá đúng mẫu lỗi.** Khi phát hiện a[mid] <= x sai, cần sửa điều kiện để phản ánh hậu điều kiện, không đặc biệt hóa riêng mảng [2, 2].
8. **Chứng minh và phân tích.** Ví dụ giúp tìm hướng chứng minh, phản ví dụ loại bỏ hướng sai; lập luận bất biến, tính kết thúc và phân tích độ phức tạp mới tạo thành lời giải có cơ sở.
9. **Lưu ca thử làm hồi quy (regression).** Sau khi sửa lỗi, giữ lại ví dụ từng làm chương trình sai để ngăn lỗi xuất hiện trở lại khi chỉnh sửa.

Có thể duy trì bảng ca kiểm thử gồm **tên ca, giả thiết/nhánh được kiểm tra, đầu vào, đầu ra kỳ vọng và nguồn suy ra kỳ vọng**. Một ca phải có mục đích rõ ràng; thêm hàng trăm bộ dữ liệu gần như giống nhau thường kém giá trị hơn một phản ví dụ đánh trúng giả định sai.

## 9. Những nhầm lẫn thường gặp

- **“Chạy đúng ví dụ mẫu là đúng thuật toán.”** Sai: ví dụ mẫu chỉ kiểm tra một số ca, không bao phủ toàn bộ miền đầu vào.
- **“Đầu vào càng lớn càng dễ tìm lỗi.”** Không nhất thiết: lỗi ranh giới có thể xuất hiện ngay với n = 0, 1 hoặc 2.
- **“Mọi đầu vào gây lỗi đều là phản ví dụ.”** Nếu đầu vào vi phạm tiền điều kiện, đó là phép thử xử lý dữ liệu không hợp lệ, chưa bác bỏ lời giải trên miền hợp lệ.
- **“Phản ví dụ phải thật phức tạp.”** Ngược lại, phản ví dụ nhỏ thường làm rõ mệnh đề sai và nguyên nhân.
- **“Hai chương trình cho cùng kết quả nên đều đúng.”** Chúng có thể chia sẻ giả định sai; cần oracle đáng tin hoặc tính chất bất biến độc lập.
- **“Đáp án đúng là một giá trị trong mảng.”** Với lower_bound, đáp án là **chỉ số**, có thể bằng n; với bài khác, đầu ra có thể là tập, đường đi, lịch hay phương án tối ưu.
- **“Kiểm thử vét cạn nhỏ đã là chứng minh.”** Nó chỉ chứng minh sự nhất quán trên miền hữu hạn đã duyệt; không thay thế chứng minh tổng quát.
- **“Một phản ví dụ bác bỏ cả một họ phương pháp.”** Nó chỉ bác bỏ khẳng định được thử; chẳng hạn thất bại của một quy tắc tham lam không phủ định mọi thuật toán tham lam.

## 10. Tự luyện

**Bài 1 — tìm phản ví dụ nhỏ.** Một bạn viết binary search với điều kiện a[mid] <= x để tìm vị trí đầu tiên ≥ x. Hãy cho một mảng đã sắp xếp có tối đa hai phần tử mà chương trình trả sai, nêu đáp án đúng và đáp án của đoạn mã sai. *Gợi ý đối chiếu:* a = [2, 2], x = 2; kết quả lower_bound là 0, biến thể trên cho 2.

**Bài 2 — xác định miền hợp lệ.** Đặc tả nói mảng có ít nhất một phần tử. Có thể lấy mảng [] để bác bỏ lời giải không xử lý rỗng không? *Đáp án:* Không; [] vi phạm tiền điều kiện. Có thể đề xuất mở rộng đặc tả hỗ trợ rỗng, nhưng đó là một yêu cầu mới.

**Bài 3 — phân biệt phản ví dụ và chứng minh.** Với các khoảng nửa mở A = [1, 4), B = [2, 3), C = [3, 5), hãy so sánh “chọn bắt đầu sớm nhất” với phương án tốt hơn. *Đáp án:* Chọn A chỉ được 1, chọn B và C được 2; bác bỏ tính tối ưu của quy tắc bắt đầu sớm nhất. Chưa đủ để chứng minh một quy tắc khác luôn tối ưu.

**Bài 4 — thiết kế bộ kiểm thử biên.** Viết ít nhất sáu ca cho lower_bound bao phủ rỗng, một phần tử, giá trị trùng, x nhỏ hơn min, x lớn hơn max và x nằm giữa hai giá trị; ghi đáp án theo **định nghĩa**, không dựa vào kết quả code. Kiểm tra thêm hậu điều kiện về chỉ số và hai phía của vị trí chèn.

## Ghi nhớ

**Ví dụ nhỏ** giúp hiểu cơ chế; **phản ví dụ** bác bỏ một khẳng định sai; **trường hợp biên** thử các ranh giới của đặc tả và cài đặt. Ba công cụ này hiệu quả nhất khi xuất phát từ **tiền điều kiện, hậu điều kiện và bất biến** rõ ràng. Hãy chọn dữ liệu có chủ đích, tìm đầu ra kỳ vọng độc lập, thu nhỏ lỗi để giải thích được nguyên nhân, rồi dùng chứng minh để khái quát kết luận vượt ra ngoài những trường hợp đã chạy thử.