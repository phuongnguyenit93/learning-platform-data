# Lời giải khả thi, hàm mục tiêu và tiêu chí tối ưu

Trong thiết kế thuật toán, nhiều bài toán không chỉ yêu cầu tìm một kết quả *đúng* mà còn yêu cầu chọn kết quả *tốt nhất* theo một tiêu chuẩn xác định. Ví dụ, một đường đi phải nối được điểm xuất phát với đích, nhưng trong số các đường đi hợp lệ ta muốn đường có tổng chi phí nhỏ nhất. Để phát biểu chính xác yêu cầu này, cần phân biệt **lời giải khả thi**, **hàm mục tiêu** và **tiêu chí tối ưu**.

## 1. Mô hình toán học của bài toán tối ưu

Với một đầu vào cụ thể (một **thể hiện bài toán**) \(I\), ta mô tả:

- **Biến quyết định** \(x\): biểu diễn phương án mà thuật toán cần chọn. Giá trị của biến phải nằm trong miền xác định, chẳng hạn số nguyên, giá trị thực, hoặc véc-tơ nhị phân.
- **Ràng buộc**: các điều kiện bắt buộc để phương án được chấp nhận.
- **Tập khả thi** \(F(I)\): toàn bộ phương án thỏa miền giá trị và mọi ràng buộc.
- **Hàm mục tiêu** \(f_I(x)\): gán cho mỗi phương án khả thi một giá trị để so sánh, chẳng hạn chi phí, thời gian, quãng đường hoặc lợi ích.
- **Chiều tối ưu hóa**: tìm giá trị nhỏ nhất (**minimize**) hoặc lớn nhất (**maximize**) của hàm mục tiêu.

Hai dạng chuẩn là:

\[
\min_{x\in F(I)} f_I(x)
\qquad\text{hoặc}\qquad
\max_{x\in F(I)} f_I(x).
\]

**Lời giải khả thi** là bất kỳ \(x\in F(I)\). **Lời giải tối ưu toàn cục** \(x^*\) là lời giải khả thi có giá trị mục tiêu không kém bất kỳ lời giải khả thi nào khác:

\[
\begin{aligned}
\text{Bài toán min: }& f_I(x^*)\le f_I(y), &&\forall y\in F(I);\\
\text{Bài toán max: }& f_I(x^*)\ge f_I(y), &&\forall y\in F(I).
\end{aligned}
\]

Giá trị \(f_I(x^*)\) gọi là **giá trị tối ưu**. Ký hiệu \(\min\) hoặc \(\max\) trả về giá trị, còn \(\arg\min\) hoặc \(\arg\max\) trả về tập các phương án đạt giá trị đó. Có thể có nhiều lời giải tối ưu cùng một giá trị mục tiêu.

Cần phân biệt ba câu hỏi: “Phương án có hợp lệ không?” (kiểm tra khả thi), “Phương án này tốt đến mức nào?” (tính hàm mục tiêu), và “Có phương án hợp lệ nào tốt hơn không?” (kiểm tra tối ưu). Trả lời được hai câu đầu **chưa đủ** để chứng minh câu thứ ba.

## 2. Ví dụ xuyên suốt: bài toán ba lô 0/1

Có bốn vật, mỗi vật chỉ được chọn một lần. Ba lô chứa tối đa 7 đơn vị trọng lượng.

| Vật \(i\) | Trọng lượng \(w_i\) | Giá trị \(v_i\) |
|---|---:|---:|
| 1 | 2 | 3 |
| 2 | 3 | 4 |
| 3 | 4 | 5 |
| 4 | 5 | 8 |

Đặt \(x_i=1\) nếu chọn vật \(i\), ngược lại \(x_i=0\). Một phương án là véc-tơ \(x=(x_1,x_2,x_3,x_4)\). Mô hình:

\[
x_i\in\{0,1\},\qquad
2x_1+3x_2+4x_3+5x_4\le 7
\]

và

\[
\max f(x)=3x_1+4x_2+5x_3+8x_4.
\]

Trong mô hình này, **không vượt sức chứa** là ràng buộc cứng; **tổng giá trị** là thứ cần tối đa hóa. Một phương án có giá trị cao nhưng vượt sức chứa không được tham gia so sánh tối ưu.

| Phương án chọn vật | Trọng lượng | Giá trị | Đánh giá |
|---|---:|---:|---|
| Không chọn vật nào | 0 | 0 | Khả thi, chưa tối ưu |
| Vật 2 và 3 | 7 | 9 | Khả thi, chưa tối ưu |
| Vật 2 và 4 | 8 | 12 | **Không khả thi** |
| Vật 1 và 4 | 7 | 11 | **Tối ưu** |

**Vì sao 11 thực sự tối ưu?** Nếu có vật 4 (nặng 5), chỉ có thể kết hợp thêm vật 1 (nặng 2); giá trị lớn nhất khi đó là \(8+3=11\). Nếu không có vật 4, ba vật 1, 2, 3 không thể lấy đồng thời vì nặng 9; cặp có giá trị cao nhất mà vẫn vừa ba lô là vật 2 và 3, đạt 9. Do đó không có phương án khả thi nào vượt 11, và \(x^*=(1,0,0,1)\) là lời giải tối ưu.

Lập luận này cung cấp đồng thời một **cận dưới** cho giá trị tối ưu của bài toán max (ta đã xây dựng được phương án đạt 11) và một **cận trên** (không phương án khả thi nào vượt 11). Hai cận bằng nhau nên đã chứng minh tối ưu.

## 3. Xác định đúng ràng buộc và hàm mục tiêu

Một đặc tả tốt phải trả lời riêng hai vấn đề:

1. **Điều gì là bắt buộc?** Ví dụ: không vượt ngân sách, đi từ đỉnh nguồn tới đỉnh đích, mỗi công việc được gán cho đúng một máy. Vi phạm một điều kiện bắt buộc khiến phương án không khả thi.
2. **Trong các phương án hợp lệ, điều gì được ưu tiên?** Ví dụ: chi phí thấp nhất, số công việc hoàn thành lớn nhất, độ trễ nhỏ nhất. Đây là hàm mục tiêu và chiều tối ưu hóa.

Ví dụ với bài toán tìm đường trên đồ thị có trọng số không âm:

- Biến quyết định: đường đi từ \(s\) tới \(t\).
- Tập khả thi: các đường đi hợp lệ từ \(s\) tới \(t\).
- Hàm mục tiêu: tổng trọng số các cạnh trên đường đi.
- Tiêu chí tối ưu: **min** tổng trọng số.

Nếu đường \(s\to a\to t\) có chi phí \(2+3=5\), còn cạnh trực tiếp \(s\to t\) có chi phí 6, thì cả hai đường đều khả thi nhưng đường qua \(a\) tốt hơn. Nếu hoàn toàn không tồn tại đường từ \(s\) tới \(t\), tập khả thi rỗng; khi ấy không thể trả về một “đường đi tối ưu” hợp lệ.

**Đơn vị đo và dấu của hàm mục tiêu phải rõ ràng.** “Tối ưu thời gian” thường có nghĩa là *giảm* thời gian; “tối ưu lợi nhuận” thường là *tăng* lợi nhuận. Không nên để từ “tối ưu” đứng một mình mà không chỉ rõ đại lượng cần so sánh. Các sở thích mềm (ví dụ “càng ít thay đổi lịch càng tốt”) có thể là mục tiêu phụ hoặc khoản phạt; không được âm thầm thay thế một ràng buộc cứng bằng khoản phạt nếu yêu cầu thực tế không cho phép vi phạm.

## 4. Những tiêu chí tối ưu cần phân biệt

### 4.1. Tối ưu toàn cục và tối ưu cục bộ

**Tối ưu toàn cục** so sánh với *toàn bộ* tập khả thi \(F(I)\). **Tối ưu cục bộ** chỉ so sánh với các phương án lân cận \(N(x)\subseteq F(I)\) theo một quy tắc biến đổi đã định nghĩa. Đối với bài toán min, \(x\) là cực tiểu cục bộ nếu \(f(x)\le f(y)\) với mọi \(y\in N(x)\); điều này không đảm bảo \(f(x)\le f(y)\) với mọi \(y\in F(I)\).

Thuật toán tìm kiếm cục bộ có thể dừng khi không tìm thấy bước cải thiện trong lân cận, dù ở một vùng khác vẫn tồn tại phương án tốt hơn. Muốn tuyên bố “tối ưu toàn cục”, cần chứng minh mạnh hơn hoặc một thuật toán có bảo đảm phù hợp với mô hình.

### 4.2. Một mục tiêu, nhiều mục tiêu và ưu tiên phụ

Với **một hàm mục tiêu**, hai phương án khả thi được so sánh trực tiếp bằng giá trị của hàm đó. Với **nhiều mục tiêu** (chẳng hạn chi phí và thời gian), không thể mặc nhiên nói phương án nào tốt hơn khi một phương án rẻ hơn nhưng chậm hơn.

Có ba cách phát biểu phổ biến:

- **Ưu tiên từ điển (lexicographic)**: tối thiểu hóa số lần vi phạm ưu tiên cao nhất trước; trong các phương án đồng hạng mới tối thiểu hóa chi phí. Thứ tự ưu tiên phải được đặc tả.
- **Gộp thành một mục tiêu có trọng số**: ví dụ \(f(x)=\alpha\cdot\text{chi phí}(x)+\beta\cdot\text{thời gian}(x)\). Phải xác định trọng số, đơn vị và quy mô của từng đại lượng; không cộng tùy tiện tiền với phút.
- **Tối ưu Pareto**: một phương án khả thi là *không bị trội* nếu không tồn tại phương án khác tốt hơn hoặc bằng trên mọi mục tiêu và tốt hơn nghiêm ngặt trên ít nhất một mục tiêu (sau khi thống nhất chiều min/max). Có thể có nhiều phương án Pareto; đây không phải một giá trị tối ưu đơn duy nhất.

Nếu có nhiều lời giải đạt cùng giá trị mục tiêu, đề bài có thể quy định tiêu chí phụ như “chọn ít vật hơn” hoặc “chọn mã nhỏ nhất”. Nếu không có, mọi lời giải cùng đạt cực trị đều tối ưu; thứ tự duyệt của chương trình không tự động trở thành tiêu chí của bài toán.

### 4.3. Tối ưu chính xác, gần đúng và heuristic

- **Tối ưu chính xác**: có bằng chứng rằng lời giải đạt giá trị tốt nhất trên tập khả thi.
- **Lời giải gần đúng có bảo đảm**: phương án vẫn phải khả thi và thuật toán có một giới hạn chất lượng được chứng minh theo điều kiện bài toán, chẳng hạn tỷ lệ xấp xỉ.
- **Heuristic**: tìm phương án có thể tốt trong thực tế nhưng không mặc nhiên có bảo đảm đạt tối ưu hay bảo đảm xấp xỉ.

Ví dụ, với bài toán max có giá trị tối ưu dương, bảo đảm \(f(x)\ge \alpha\,\mathrm{OPT}\) (\(0<\alpha\le1\)) có nghĩa là lời giải đạt ít nhất tỷ lệ \(\alpha\) của tối ưu. Không được sử dụng tỷ lệ như vậy khi chưa chứng minh giả thiết và bảo đảm của thuật toán.

**Chất lượng lời giải** khác với **hiệu năng thuật toán**: chạy nhanh hơn không có nghĩa là đạt hàm mục tiêu tốt hơn. Một thuật toán có thời gian \(O(n\log n)\) không vì vậy mà tự động “tối ưu” về chi phí, quãng đường hoặc lợi ích của bài toán.

## 5. Chứng minh một phương án tối ưu

Với bài toán **max**, bất cứ lời giải khả thi có giá trị \(L\) nào đều cho biết \(\mathrm{OPT}\ge L\). Nếu đồng thời chứng minh được mọi phương án khả thi có giá trị không vượt \(U\), tức \(\mathrm{OPT}\le U\), thì \(L=U\) xác nhận tối ưu.

Với bài toán **min**, một lời giải khả thi giá trị \(U\) cho \(\mathrm{OPT}\le U\); một chứng minh mọi phương án có chi phí ít nhất \(L\) cho \(\mathrm{OPT}\ge L\). Một lần nữa, khi \(L=U\), lời giải đã đạt tối ưu.

Các cách xây dựng chứng minh thường gặp:

- **Liệt kê đầy đủ** tập khả thi khi số phương án đủ nhỏ, như ví dụ bốn vật.
- **Chứng minh lựa chọn tham lam** bằng tính chất lựa chọn tham lam, lập luận trao đổi hoặc bất biến thích hợp; không phải mọi bài toán tối ưu đều dùng được greedy.
- **Quy hoạch động**: xác định trạng thái, công thức truy hồi và chứng minh các trạng thái bao quát các lựa chọn cần xét.
- **Nhánh và cận**: duy trì một lời giải khả thi và cận để loại các nhánh không thể cải thiện đáp án.

Chỉ tính được \(f(x)\) cho một phương án, hoặc thử nhiều phương án nhưng chưa bao phủ đủ trường hợp, không phải chứng minh tối ưu.

## 6. Ví dụ Java 17+: kiểm tra khả thi và tìm tối ưu

Chương trình sau duyệt mọi tập con của bốn vật. Mỗi bit của **mask** cho biết có chọn một vật hay không. Đầu tiên tính trọng lượng và giá trị, **loại phương án không khả thi**, sau đó mới so sánh giá trị để cập nhật lời giải tốt nhất.

Lưu thành tệp **KnapsackOptimization.java**:

~~~java
public class KnapsackOptimization {
    public static void main(String[] args) {
        int[] weights = {2, 3, 4, 5};
        int[] values = {3, 4, 5, 8};
        int capacity = 7;
        int n = weights.length;

        int bestMask = -1;
        int bestWeight = 0;
        int bestValue = Integer.MIN_VALUE;

        for (int mask = 0; mask < (1 << n); mask++) {
            int totalWeight = 0;
            int totalValue = 0;

            for (int i = 0; i < n; i++) {
                if ((mask & (1 << i)) != 0) {
                    totalWeight += weights[i];
                    totalValue += values[i];
                }
            }

            if (totalWeight > capacity) {
                continue; // Phuong an khong kha thi
            }

            if (bestMask == -1 || totalValue > bestValue) {
                bestMask = mask;
                bestWeight = totalWeight;
                bestValue = totalValue;
            }
        }

        System.out.println("Best value: " + bestValue);
        System.out.println("Total weight: " + bestWeight);
        System.out.print("Selected items:");
        for (int i = 0; i < n; i++) {
            if ((bestMask & (1 << i)) != 0) {
                System.out.print(" " + (i + 1));
            }
        }
        System.out.println();
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac KnapsackOptimization.java
java KnapsackOptimization
~~~

Kết quả chuẩn:

~~~text
Best value: 11
Total weight: 7
Selected items: 1 4
~~~

Chương trình tìm được tập vật 1 và 4, đúng với chứng minh ở phần 2. Vì duyệt hết \(2^n\) tập con và xét tối đa \(n\) vật trên mỗi tập, thời gian là \(O(n2^n)\); cách này thích hợp để minh họa và kiểm tra các thể hiện nhỏ. Biểu thức dịch bit dùng kiểu \`int\` chỉ phù hợp với \(n\) nhỏ (ở đây \(n=4\)); không được xem đây là một triển khai tổng quát cho số lượng vật rất lớn. Với đầu vào lớn cần cân nhắc quy hoạch động, nhánh và cận hoặc thuật toán gần đúng tùy giả thiết về trọng lượng, giá trị và yêu cầu chất lượng.

## 7. Trường hợp biên ảnh hưởng đến phát biểu “tối ưu”

- **Tập khả thi rỗng**: không có lời giải hợp lệ. Ví dụ, yêu cầu \(x\ge0\) đồng thời \(x\le-1\). Không nên trả một giá trị mục tiêu giả rồi gọi đó là tối ưu.
- **Bài toán không bị chặn**: có lời giải khả thi nhưng mục tiêu có thể tốt lên vô hạn; ví dụ \(\max x\) với \(x\ge0\) không có giá trị tối ưu hữu hạn.
- **Có cận tối ưu nhưng không đạt được**: với \(0<x<1\), bài toán \(\max x\) có cận trên đúng bằng 1 nhưng không có phương án khả thi nào đạt 1. Cần phân biệt *supremum* với *maximum* khi tập khả thi không đóng.
- **Nhiều lời giải tối ưu**: hai phương án khác nhau có thể có cùng giá trị tốt nhất. Tính duy nhất chỉ có khi bài toán hoặc tiêu chí phụ bảo đảm điều đó.
- **Mô hình thiếu hoặc sai ràng buộc**: thuật toán có thể giải đúng mô hình đã viết nhưng kết quả không đáp ứng yêu cầu thực tế. Tính tối ưu luôn phụ thuộc vào cách mô hình hóa và thể hiện đầu vào.

## 8. Quy trình đặc tả và kiểm tra một bài toán tối ưu

1. Xác định rõ một **thể hiện đầu vào** và định dạng **phương án đầu ra**.
2. Chọn **biến quyết định và miền giá trị** đủ biểu diễn mọi phương án hợp lệ cần xét.
3. Viết **tất cả ràng buộc cứng** để định nghĩa tập khả thi; kiểm tra cả trường hợp không có phương án nào hợp lệ.
4. Xác định **hàm mục tiêu**, đơn vị đo, chiều min/max và thứ tự ưu tiên nếu có nhiều tiêu chí.
5. Phân biệt yêu cầu chỉ tìm **một lời giải khả thi** với yêu cầu tìm **lời giải tối ưu**. Nếu cần chứng minh tối ưu, nêu cách chứng minh hoặc bảo đảm thuật toán.
6. Thử các ví dụ nhỏ: phương án hợp lệ nhưng kém hơn, phương án hấp dẫn nhưng vi phạm ràng buộc, phương án đạt tối ưu và trường hợp biên.

**Câu hỏi tự kiểm tra:** Với ba lô ở phần 2, phương án chọn vật 2 và 4 có tổng giá trị 12, lớn hơn 11. Tại sao không được chọn làm đáp án? **Đáp án:** trọng lượng \(3+5=8>7\) vi phạm ràng buộc; hàm mục tiêu chỉ được tối ưu trên tập phương án khả thi.