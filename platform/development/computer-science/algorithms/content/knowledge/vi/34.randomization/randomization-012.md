# Kiểm thử phân bố thay vì chỉ kiểm tra một lần chạy

**Kiểm thử thuật toán ngẫu nhiên hóa** không thể chỉ kiểm tra một lần chạy cho ra kết quả hợp lệ. Một thuật toán có thể luôn trả một giá trị đúng kiểu, một hoán vị hợp lệ hoặc một mẫu đúng kích thước nhưng lại **thiên lệch xác suất**, **phụ thuộc mạnh giữa các lần gọi** hoặc **không đạt xác suất thành công đã cam kết**. Vì vậy cần kết hợp **kiểm tra tính đúng của từng đầu ra** với **kiểm tra tính chất của nhiều lần chạy theo phân bố kỳ vọng**.

Bài học thuộc nhóm **Ngẫu nhiên hóa** của Computer Science Algorithms, tập trung đúng chủ đề **“Kiểm thử phân bố thay vì chỉ kiểm tra một lần chạy”**. Ta sẽ dùng bốn thí nghiệm: xúc xắc cân bằng và có thiên lệch, Fisher–Yates shuffle so với xáo trộn sai, dãy tuần hoàn có tần suất đều nhưng thiếu tính độc lập, và biến ngẫu nhiên liên tục với kiểm định Kolmogorov–Smirnov. Bài gồm giả thuyết thống kê, mức ý nghĩa, kích thước mẫu, cách tránh kiểm định sai giả thiết, kiểm thử thực nghiệm Java 17+ với seed cố định, kiểm tra giải tích độc lập, cách diễn giải kết quả và bài tập.

## 1. Vì sao một lần chạy chưa đủ?

Giả sử hàm `rollDie()` trả một số nguyên từ 0 đến 5.

Một phép thử đơn:

~~~java
int face = random.nextInt(6);
if (face < 0 || face >= 6) {
    throw new AssertionError("Invalid die face");
}
~~~

chỉ xác nhận **đầu ra hợp lệ**, không chứng minh các mặt có cùng xác suất. Hai bộ sinh sau đều vượt kiểm tra phạm vi:

- Bộ sinh A: mỗi mặt 0,1,2,3,4,5 có xác suất 1/6.
- Bộ sinh B: mặt 0 có xác suất cao hơn, các mặt khác thấp hơn, nhưng kết quả luôn trong 0..5.

Nếu bộ sinh B trả 3 trong một lượt, không có dấu hiệu nào trong **riêng lượt đó** để phát hiện thiên lệch. Ngay cả 100 lượt đều hợp lệ cũng không chứng minh xác suất chính xác.

Tương tự, một hàm xáo trộn mảng có thể luôn bảo toàn mọi phần tử và vẫn **ưu tiên một số hoán vị**. Một thuật toán lấy mẫu có thể luôn trả đúng k phần tử phân biệt mà một số phần tử xuất hiện nhiều hơn xác suất được yêu cầu.

**Kết luận:** đầu ra đúng về cấu trúc là **điều kiện cần**, không phải bảo đảm về phân bố.

## 2. Ba lớp kiểm thử nên tách riêng

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Bất biến chức năng** | Mỗi đầu ra có hợp lệ không? | Shuffle giữ nguyên tập phần tử; xúc xắc trong 0..5 |
| **Phân bố biên (marginal distribution)** | Khi chạy nhiều lần, mỗi loại kết quả có tần suất phù hợp không? | Sáu mặt gần 1/6; sáu hoán vị n=3 gần 1/6 |
| **Phụ thuộc giữa các kết quả** | Chuỗi kết quả có tương quan/pattern bất thường không? | Dãy 0,1,2,3,4,5 lặp lại có tần suất đều nhưng hoàn toàn dự đoán được |

Ba lớp bổ sung nhau. Một phân bố biên cân bằng không có nghĩa các mẫu độc lập; một chuỗi khó đoán không đảm bảo mọi biến cố có xác suất đúng; và một phép kiểm xác suất không thay thế chứng minh tính đúng của thuật toán.

Khi thuật toán có tính chất khác, như **xác suất thành công ít nhất 99%**, **ước lượng Monte Carlo không chệch** hoặc **độ dài lời giải ngẫu nhiên**, ta phải chọn phép kiểm dựa trên **đại lượng mà đặc tả yêu cầu**, không ép tất cả bài vào kiểm định đều.

## 3. Quy trình kiểm thử phân bố

Để tạo một phép kiểm có ý nghĩa:

1. **Nêu rõ phân bố kỳ vọng:** các giá trị nào có thể xuất hiện, với xác suất bao nhiêu? Với shuffle n phần tử phân biệt, mọi hoán vị có được yêu cầu đồng xác suất 1/n! không?
2. **Nêu giả thuyết gốc H₀:** ví dụ `P(X=i)=1/6` cho i=0..5. Giả thuyết đối H₁ là phân bố thực tế **không** đáp ứng H₀.
3. **Chọn thống kê kiểm định:** đếm tần suất, chi-square cho nhóm rời rạc, KS cho phân bố liên tục đã biết, hay thống kê đặc thù của thuật toán.
4. **Chọn số mẫu N và mức ý nghĩa α trước khi quan sát dữ liệu:** chẳng hạn α=0.01 (1%).
5. **Dùng các mẫu đúng giả thiết:** kiểm định chi-square multinomial chuẩn cần các lượt lấy mẫu độc lập và cùng phân bố dưới H₀; nếu các quan sát phụ thuộc, phải thiết kế/cân chỉnh thống kê khác.
6. **Tính thống kê và so với ngưỡng:** không kết luận chỉ vì một tần suất trông “khá đều”.
7. **Phân tích sai số và sức mạnh kiểm định:** một phép kiểm không bác bỏ H₀ vẫn có thể bỏ sót độ lệch nhỏ.
8. **Lưu seed, số mẫu, phiên bản mã và thống kê:** để tái tạo thất bại và phân biệt lỗi triển khai với nhiễu ngẫu nhiên.
9. **Không dò nhiều seed rồi chọn seed vượt kiểm định:** hành động ấy biến bài test thành bộ lọc kết quả thuận lợi, làm sai mức ý nghĩa.
10. **Kết hợp với chứng minh và oracle độc lập:** khi có thể liệt kê chính xác không gian xác suất nhỏ, chứng minh đó mạnh hơn một thí nghiệm hữu hạn.

## 4. Kiểm định chi-square cho phân bố rời rạc

Giả sử có k kết quả rời rạc với xác suất kỳ vọng `p₀,…,p_(k−1)`, trong đó `Σpᵢ=1`.

Sau N phép lấy mẫu, gọi `Oᵢ` là số lần thấy kết quả i. Số lần kỳ vọng dưới H₀ là:

`Eᵢ=Npᵢ`.

**Thống kê Pearson chi-square:**

`χ²=Σ_(i=0)^(k−1) (Oᵢ−Eᵢ)²/Eᵢ`.

Giá trị χ² **càng lớn**, tần suất thực nghiệm càng xa phân bố được giả định. Nếu tham số xác suất đã biết trước và các quan sát độc lập, khi số mẫu đủ lớn, χ² thường được so với phân bố chi-square có **k−1 bậc tự do**.

Trường hợp phân bố đều k loại:

`pᵢ=1/k`, `Eᵢ=N/k`.

Với sáu mặt xúc xắc (k=6), bậc tự do là 5. Ở mức ý nghĩa **α=0.01**, ngưỡng phía trên của phân bố χ² với 5 bậc tự do xấp xỉ **15.086**.

- Nếu `χ²>15.086`: **bác bỏ H₀** ở mức kiểm định đã đặt, có bằng chứng thống kê của sự không phù hợp.
- Nếu `χ²≤15.086`: **chưa đủ bằng chứng bác bỏ H₀**; **không** được nói đã chứng minh phân bố thực sự hoàn toàn đồng đều.

### Điều kiện áp dụng

Cần đặc biệt chú ý:

- Các lần quan sát thực sự độc lập hoặc dùng một mô hình đủ gần giả thiết kiểm định; với một PRNG cố định, tính độc lập chỉ là mô hình gần đúng, không phải tính ngẫu nhiên toán học tuyệt đối.
- Nhóm phân loại phải không giao nhau và bao phủ các khả năng cần kiểm tra.
- Số lần kỳ vọng Eᵢ đủ lớn để dùng xấp xỉ chi-square, quy tắc thực hành phổ biến là **Eᵢ≥5**. Khi một số nhóm rất hiếm, nên gộp nhóm có căn cứ hoặc chọn kiểm định exact/Monte Carlo phù hợp.
- Nếu `pᵢ` được **ước lượng từ chính dữ liệu kiểm định**, bậc tự do hoặc phân bố chuẩn của thống kê có thể thay đổi; không áp dụng máy móc k−1.
- Nếu ta chạy **nhiều phép kiểm**, mức α=1% của từng phép kiểm không còn là mức sai dương của toàn bộ chiến dịch.

### Ví dụ tự tính

Giả sử N=120 lần gieo xúc xắc đều, E=20 mỗi mặt. Nếu thấy:

`O=[20,20,20,20,20,20]`,

thì χ²=0.

Nếu thấy:

`O=[60,12,12,12,12,12]`,

thì:

`χ²=(60−20)²/20+5·(12−20)²/20`

`=80+16=96`.

Vì 96 lớn hơn 15.086, ta bác bỏ giả thuyết sáu mặt đồng xác suất. Tuy nhiên thống kê lớn **không tự nói nguyên nhân**: có thể do phép ánh xạ sai, mẫu không độc lập hoặc chính giả thuyết kiểm định không đúng theo yêu cầu thực tế.

## 5. Xúc xắc chuẩn so với xúc xắc bị thiên lệch

Bộ sinh chuẩn trong Java:

~~~java
int face = random.nextInt(6);
~~~

Với mô hình `Random.nextInt(bound)`, mỗi giá trị nguyên trong [0,bound) được chọn đồng đều theo thiết kế bộ sinh. Trong thực nghiệm, ta đánh giá **đầu ra thực hiện của mã** dưới mô hình phù hợp, không biến một phép kiểm thống kê thành chứng minh hoàn hảo của nguồn PRNG.

Bộ sinh sai cố ý:

~~~java
int face = random.nextInt(6) == 0
        ? 0
        : random.nextInt(6);
~~~

Phân tích xác suất:

- Nhánh đầu có xác suất 1/6 và trả thẳng mặt 0.
- Nếu nhánh đầu khác 0 (xác suất 5/6), chương trình gieo thêm lần nữa, lúc ấy mỗi mặt có xác suất 1/6.
- Vì vậy:

`P(face=0)=1/6+(5/6)(1/6)=11/36≈0.30556`.

Với các mặt i=1..5:

`P(face=i)=(5/6)(1/6)=5/36≈0.13889`.

Tổng `11/36+5·5/36=1`. Kết quả **luôn trong 0..5** nhưng không đồng đều.

### Thí nghiệm với 120.000 lượt

N=120000, mỗi mặt của H₀ có kỳ vọng E=20000. Dưới seed minh họa của chương trình Java:

~~~text
dieFair counts=[20032, 20148, 19958, 19829, 19962, 20071] chi2=3.021 decision=PASS
dieBiased counts=[36547, 16623, 16734, 16539, 16896, 16661] chi2=16431.818 decision=REJECT
~~~

Dòng PASS nghĩa là **không bác bỏ H₀ trong phép kiểm này**, không phải chứng nhận thuật toán hoàn hảo. Dòng REJECT cho thấy mẫu có độ lệch rất lớn so với H₀. Nhìn từng mẫu một, cả hai thuật toán đều trông hợp lệ.

### Độ lệch theo đơn vị xác suất

Với p=1/6 và N=120000, độ lệch chuẩn của tỉ lệ một mặt trong mô hình binomial độc lập là:

`SE=√[p(1−p)/N]≈0.001076`.

Độ lệch thực tế của mặt 0 trong bộ sinh sai, khoảng 0.30556−0.16667≈0.13889, lớn hơn SE rất nhiều. Mặt khác, một bộ sinh chỉ lệch vài phần mười phần trăm có thể khó bị phát hiện nếu N nhỏ; không được đặt N chỉ dựa trên “chạy vài lần thấy đều”.

## 6. Kiểm tra phân bố hoán vị sau Fisher–Yates shuffle

Với m phần tử **phân biệt**, một thuật toán xáo trộn đều phải cho mỗi hoán vị xác suất:

`1/m!`.

**Fisher–Yates chuẩn**:

~~~text
SHUFFLE(a):
    for i = length(a)-1 down to 1:
        j = uniform integer in [0,i]
        swap(a[i],a[j])
~~~

Ở mỗi bước, vị trí i nhận một trong i+1 phần tử còn lại đồng xác suất; sau đó vị trí ấy không bị thay đổi nữa. Xác suất của **mỗi hoán vị cụ thể** là:

`(1/m)·(1/(m−1))·…·(1/2)·1=1/m!`.

Điều kiện quan trọng là `j` được chọn **trong [0,i]**, không phải [0,m−1] cho mọi i.

### Phản ví dụ xáo trộn sai

Thuật toán sai phổ biến:

~~~text
BAD_SHUFFLE(a):
    for i = 0 to length(a)-1:
        j = uniform integer in [0,length(a)-1]
        swap(a[i],a[j])
~~~

Thuật toán này **vẫn giữ nguyên các phần tử**, nhưng không đảm bảo mọi hoán vị có xác suất ngang nhau.

Với m=3, có **3³=27 chuỗi lựa chọn j** đồng xác suất. Mỗi chuỗi dẫn tới một hoán vị. Ta có thể **liệt kê chính xác toàn bộ 27 chuỗi**, không cần giả lập, để nhận số lần mỗi hoán vị xảy ra:

| Hoán vị | Số chuỗi j tạo hoán vị | Xác suất thực |
| --- | ---: | ---: |
| [0,1,2] | 4 | 4/27 |
| [0,2,1] | 5 | 5/27 |
| [1,0,2] | 5 | 5/27 |
| [1,2,0] | 5 | 5/27 |
| [2,0,1] | 4 | 4/27 |
| [2,1,0] | 4 | 4/27 |

Phân bố đều yêu cầu mỗi hoán vị có xác suất 1/6=4.5/27. Vì số chuỗi tạo ra từng hoán vị không đồng đều, thuật toán sai bị **bác bỏ bằng suy luận tổ hợp chính xác**, không chỉ bởi một kiểm định thống kê.

### Thống kê khi mô phỏng 120.000 lần

Với m=3, chỉ có 6 hoán vị nên có thể đếm đủ cả sáu nhóm. Ngưỡng chi-square df=5, α=1% vẫn là 15.086.

~~~text
shuffleFair counts=[19948, 19873, 20196, 20268, 19763, 19952] chi2=9.377 decision=PASS
shuffleBiased counts=[17870, 22284, 21943, 22266, 17872, 17765] chi2=1409.359 decision=REJECT
badShuffleExactPaths=[4, 5, 5, 5, 4, 4]
~~~

Trong ví dụ nhỏ, có thể gán mỗi hoán vị một **chỉ số 0..5** bằng mã thứ tự (Lehmer rank/factoradic). Nếu m lớn, không nên tự tạo m! bộ đếm: bộ nhớ bùng nổ và nhiều nhóm có kỳ vọng nhỏ hơn 5. Khi ấy cần chọn thống kê có cấu trúc, như tần suất phần tử ở mỗi vị trí, phân bố một thuộc tính hoán vị hoặc phương pháp tổ hợp khác, kết hợp với chứng minh thuật toán.

**Lưu ý:** chỉ kiểm tra một phần tử có xuất hiện ở mỗi vị trí gần 1/m là **chưa đủ chứng minh hoán vị đều**. Có thể có phân bố không đều trên m! hoán vị mà tất cả phân bố vị trí riêng lẻ vẫn cân bằng.

## 7. Phân bố từng lượt đều nhưng chuỗi vẫn sai

Xét một bộ sinh cực kỳ đơn giản:

~~~text
0,1,2,3,4,5,0,1,2,3,4,5,0,1,2,3,4,5,...
~~~

Sau 120.000 phần tử, mỗi mặt xuất hiện đúng 20.000 lần:

`counts=[20000,20000,20000,20000,20000,20000]`.

Thống kê chi-square của tần suất **bằng 0**, phù hợp tuyệt đối với kỳ vọng sáu nhóm. Tuy nhiên toàn bộ chuỗi **hoàn toàn xác định và dự đoán được**. Vì vậy không thể đánh đồng “tần suất đều” với “các kết quả độc lập”.

### Kiểm tra cặp liên tiếp **không chồng lấn**

Một phép kiểm phụ thuộc đơn giản là gom các lượt theo cặp:

`(X₀,X₁),(X₂,X₃),(X₄,X₅),…`.

Chọn thuộc tính **chẵn/lẻ** của mỗi thành phần, tạo bốn loại cặp:

- `EE`: chẵn–chẵn.
- `EO`: chẵn–lẻ.
- `OE`: lẻ–chẵn.
- `OO`: lẻ–lẻ.

Nếu mỗi X là một mặt xúc xắc đều **và độc lập**, mỗi loại có xác suất 1/4. Với 120.000 kết quả, ta có **60.000 cặp không chồng lấn**, E=15.000 mỗi nhóm, thống kê chi-square có xấp xỉ df=3, ngưỡng α=1% khoảng **11.345**.

**Vì sao bắt buộc không chồng lấn trong ví dụ này?** Các cặp trượt `(X₀,X₁),(X₁,X₂),…` chia sẻ quan sát và không độc lập. Nếu vẫn dùng công thức critical value của multinomial độc lập một cách máy móc, p-value có thể bị hiệu chỉnh sai. Cặp không chồng lấn giúp giả thiết iid của các nhóm kiểm thử được rõ ràng hơn khi nguồn thực sự iid.

Với bộ sinh ngẫu nhiên phù hợp:

~~~text
serialRandom counts=[14912, 14883, 15117, 15088] chi2=2.858 decision=PASS
~~~

Với bộ sinh tuần hoàn:

~~~text
periodicMarginal counts=[20000, 20000, 20000, 20000, 20000, 20000] chi2=0.000 decision=PASS
serialPeriodic counts=[0, 60000, 0, 0] chi2=180000.000 decision=REJECT
~~~

Bởi mỗi cặp trong chu kỳ trên là **chẵn→lẻ**, nên cả 60.000 cặp đều rơi vào một nhóm. Đây là ví dụ cho thấy **một phân bố biên hoàn hảo vẫn có thể đi cùng phụ thuộc nghiêm trọng**.

### Phép kiểm cặp có giới hạn

Một chuỗi có thể qua phép kiểm tần suất và các cặp chẵn/lẻ nhưng vẫn có cấu trúc bất thường ở các vị trí khác (chu kỳ dài hơn, phụ thuộc bậc cao). Kiểm thử nghiêm túc có thể cần thêm autocorrelation theo nhiều lag, runs test, kiểm thử mẫu bit, tính chất liên quan đến thuật toán tiêu thụ các số ngẫu nhiên và bộ kiểm thử PRNG chuyên dụng.

Một vài phép kiểm phân bố **không phải chứng nhận an toàn mật mã**. `java.util.Random` là PRNG phục vụ mô phỏng thông thường, không phải nguồn bí mật khó dự đoán; các ứng dụng bảo mật cần lớp sinh số như `SecureRandom` và thiết kế an toàn phù hợp.

## 8. Kiểm định Kolmogorov–Smirnov cho phân bố liên tục

Không phải thuật toán ngẫu nhiên nào cũng trả số nguyên hữu hạn. Với biến thực `U` kỳ vọng đồng đều trên [0,1), ta có hàm phân phối tích lũy lý thuyết:

`F(x)=0` nếu x<0,

`F(x)=x` nếu 0≤x≤1,

`F(x)=1` nếu x>1.

Lấy N quan sát liên tục độc lập, sắp tăng:

`u_(1)≤u_(2)≤…≤u_(N)`.

**Thống kê Kolmogorov–Smirnov một mẫu hai phía:**

`D_N = max_i { i/N−u_(i), u_(i)−(i−1)/N }`.

D_N đo độ lệch tối đa giữa **hàm phân phối thực nghiệm** và F(x). Với H₀ là phân phối liên tục đã xác định hoàn toàn, một ngưỡng tiệm cận thông dụng tại **α≈0.01** là:

`D_critical≈1.63/√N`.

Với N=20.000:

`1.63/√20000≈0.01153`.

### Hai bộ sinh biến thực

- Bộ sinh chuẩn: `U=random.nextDouble()`.
- Bộ sinh bị biến đổi: `V=U²`.

V luôn nằm trong [0,1), nên kiểm tra phạm vi **không phát hiện lỗi**. Nhưng:

`P(V≤v)=P(U≤√v)=√v`, với v∈[0,1].

Đây **không** phải hàm phân phối đều `F(v)=v`; V thiên về các số gần 0.

Thí nghiệm Java với N=20.000:

~~~text
ksUniform D=0.00520 cutoff=0.01153 decision=PASS
ksSquare D=0.24934 cutoff=0.01153 decision=REJECT
~~~

Tại sao D của V lớn? Hiệu `√v−v` đạt giá trị lớn nhất 1/4 tại v=1/4, nên khi N lớn, D thực nghiệm có xu hướng gần 0.25. Thí nghiệm cho xấp xỉ 0.24934, phù hợp giải thích giải tích.

### Không áp KS sai ngữ cảnh

- KS một mẫu với ngưỡng tiêu chuẩn yêu cầu phân bố tham chiếu **liên tục và đã biết**; dữ liệu rời rạc có nhiều ties làm thay đổi cách hiệu chỉnh p-value.
- Nếu ước lượng tham số F từ **chính dữ liệu**, critical value chuẩn KS có thể không còn đúng.
- Với một nguồn có phụ thuộc thời gian, phân bố của D_N cũng thay đổi.
- N=20.000 và hệ số 1.63 là **xấp xỉ tiệm cận**. Nếu cần kiểm định chính xác với mẫu nhỏ hoặc cấu trúc khác, dùng phân bố exact hay phương pháp hiệu chỉnh/Monte Carlo thích hợp.
- KS kiểm tra phân bố biên, **không** kiểm tra tính độc lập; cần lớp kiểm thử chuỗi riêng.

## 9. Kích thước mẫu, sai dương và công suất kiểm định

### 9.1. Sai dương (Type I error)

Đặt mức ý nghĩa α=0.01 có nghĩa: **nếu H₀ thật và giả thiết kiểm định được thỏa mãn**, xác suất bác bỏ H₀ khoảng 1% cho một phép kiểm được định trước. Do đó **một thuật toán đúng vẫn có thể bị báo REJECT bởi nhiễu mẫu**.

Không nên gắn một phép kiểm xác suất với ngưỡng nghiêm ngặt làm điều kiện CI bắt buộc trên mỗi build với seed thay đổi liên tục rồi gọi mọi REJECT là lỗi chắc chắn. Có thể giữ bộ seed xác định làm **regression fixture**, thu thập thống kê thêm khi test báo bất thường, và xây chính sách kiểm định tổng thể có tính đến sai dương.

### 9.2. Sai âm (Type II error)

Khi H₀ sai nhưng phép kiểm không bác bỏ, ta có **sai âm**. Khả năng phát hiện phụ thuộc:

- Mức độ thiên lệch thật sự (effect size).
- Kích thước mẫu N.
- Thống kê kiểm định có nhạy với kiểu lỗi hay không.
- Mức ý nghĩa α.
- Giả thiết độc lập, phân phối và quy tắc dừng.

**Power (công suất)** là xác suất bác bỏ H₀ khi một phân bố thay thế cụ thể đúng: `power=1−β`. Tăng N thường tăng khả năng phát hiện một độ lệch cố định, nhưng cũng tăng chi phí chạy.

### 9.3. Chọn N theo độ chính xác mong muốn

Với một biến cố có xác suất p, tỉ lệ thực nghiệm `p̂` trên N lượt độc lập có:

`SE(p̂)=√[p(1−p)/N]`.

Một khoảng xấp xỉ 95% theo chuẩn thông thường là:

`p̂ ± 1.96·√[p̂(1−p̂)/N]`,

khi N đủ lớn và các điều kiện xấp xỉ phù hợp. Với xác suất nhỏ hoặc N ít, khoảng **Wilson** hoặc kiểm định exact binomial thường thích hợp hơn khoảng đối xứng đơn giản này.

Để có một sai số tỉ lệ cỡ δ với mức tin cậy cho trước, chi phí mẫu thường tăng như:

`N=Θ(1/δ²)`,

nên muốn sai số nhỏ đi 10 lần có thể cần khoảng 100 lần số mẫu. Đây là thước đo để thiết kế test chứ không phải lời hứa một cỡ mẫu bất kỳ sẽ phát hiện mọi lỗi.

### 9.4. Nhiều phép kiểm: tránh p-hacking

Nếu chạy m kiểm định độc lập, mỗi phép dùng α=0.01, xác suất có **ít nhất một** bác bỏ nhầm khi tất cả H₀ đúng là:

`1−(1−0.01)^m`.

Với m=10, giá trị xấp xỉ **9.56%**. Các phép kiểm không độc lập có xác suất tổng hợp khác, nhưng nguy cơ sai dương tích lũy vẫn cần xử lý.

Một phương án kiểm soát xác suất có ít nhất một sai dương (family-wise error rate) là **Bonferroni**: dùng ngưỡng α/m cho mỗi phép kiểm nếu muốn giới hạn tổng mức sai dương bởi α, ngay cả khi các phép kiểm có phụ thuộc.

**Đặc biệt không nên thử nhiều seed cho đến khi gặp một kết quả PASS**, vì đó là chọn kết quả sau khi quan sát dữ liệu. Seed phục vụ khả năng tái hiện phải được xác định trước và ghi lại.

## 10. Seed, tính tái lập và nguồn ngẫu nhiên

### Seed cố định cho regression test

`new Random(2026L)` tạo một chuỗi xác định theo cài đặt PRNG của Java. Khi chạy cùng chương trình với cùng seed và cùng thứ tự gọi, kết quả được tái hiện, giúp điều tra lỗi.

Đối với một phép thử phân bố nhiều lần, **khởi tạo Random một lần trước vòng lấy mẫu**:

~~~java
Random random = new Random(2026L);
for (int t = 0; t < 120_000; t++) {
    int face = random.nextInt(6);
    // Ghi nhận face.
}
~~~

**Không tạo `new Random(2026L)` bên trong từng lượt**, vì khi ấy mỗi lần ta lấy phần tử đầu của **cùng một chuỗi**, dẫn đến kết quả giống nhau, không phải một loạt phép lấy mẫu.

### Seed tái lập không phải độc lập toán học tuyệt đối

Một PRNG có trạng thái hữu hạn sinh chuỗi xác định. Khi nói kết quả “iid” trong kiểm định, đó thường là **mô hình thống kê mong muốn** của chuỗi được sinh. Nếu thuật toán yêu cầu bảo đảm xác suất lý thuyết, chứng minh phải bắt đầu từ **mô hình random bits/PRNG** đã chọn, không chỉ từ PASS của một bộ test.

### Kiểm thử hồi quy và kiểm thử khám phá

- **Regression:** seed cố định, đầu ra cụ thể hoặc checksum cụ thể, kiểm tra bất biến và các tình huống lỗi đã biết.
- **Distribution test:** seed được đặt trước, N đủ lớn, thống kê và ngưỡng được báo; cần chấp nhận khả năng sai dương.
- **Exploratory testing:** chạy nhiều seed để tìm lỗi thực thi, ghi seed gây lỗi, nhưng không dùng việc chỉ giữ những seed PASS để khẳng định phân bố tốt.

Một số hệ thống cần nhiều luồng chạy song song. Khi đó phải tránh vô tình cho nhiều luồng **cùng một seed và cùng thứ tự thao tác**, vì dữ liệu bị nhân bản và tính độc lập giả định của phép thống kê bị phá vỡ.

## 11. Mã Java 17+: kiểm thử rời rạc, hoán vị, độc lập và liên tục

Bản demo sử dụng các phép kiểm có thể tái hiện được, chia rõ **thống kê**, **oracle tổ hợp** và **quyết định theo ngưỡng**.

- Xúc xắc: đếm 120.000 giá trị 0..5; chi-square df=5 với ngưỡng 15.086.
- Fisher–Yates và shuffle sai: mã hóa đủ sáu hoán vị m=3; chi-square df=5.
- Liệt kê độc lập **27 đường đi** của shuffle sai; đây là **chứng minh phân bố chính xác**, không phải kiểm định ngẫu nhiên.
- Dãy tuần hoàn: kiểm tra phân bố từng mặt và **cặp không chồng lấn** chẵn/lẻ, chi-square df=3 với ngưỡng 11.345.
- KS: 20.000 số thực trên [0,1), thống kê D và ngưỡng tiệm cận.
- Kiểm thử chức năng: mọi lần gieo đều trong 0..5, seed cố định lặp lại chuỗi, shuffle luôn là hoán vị.
- Kiểm thử công thức chi-square bằng bộ đếm có kết quả biết trước.

Cú pháp và giao diện tương thích **JDK 17+**. Lưu thành **`DistributionTestingDemo.java`**.

### Toàn bộ mã nguồn

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.Random;

public class DistributionTestingDemo {
    static final int TRIALS = 120_000;
    static final int CONTINUOUS_SAMPLES = 20_000;

    // Chi-square upper 1% critical values: df=5 and df=3.
    static final double CHI6_1_PERCENT = 15.086;
    static final double CHI4_1_PERCENT = 11.345;

    @FunctionalInterface
    interface IntSampler {
        int sample(Random random);
    }

    static int fairDie(Random random) {
        return random.nextInt(6);
    }

    static int biasedDie(Random random) {
        return random.nextInt(6) == 0
                ? 0 : random.nextInt(6);
    }

    static int[] histogram(
            long seed, int draws, int categories,
            IntSampler sampler) {
        if (draws <= 0 || categories < 2) {
            throw new IllegalArgumentException(
                    "Invalid histogram dimensions");
        }
        int[] counts = new int[categories];
        Random random = new Random(seed);
        for (int t = 0; t < draws; t++) {
            int value = sampler.sample(random);
            if (value < 0 || value >= categories) {
                throw new AssertionError("Sample out of range");
            }
            counts[value]++;
        }
        return counts;
    }

    static double chiSquareUniform(int[] counts) {
        if (counts == null || counts.length < 2) {
            throw new IllegalArgumentException("Invalid categories");
        }
        long total = 0L;
        for (int v : counts) {
            if (v < 0) throw new IllegalArgumentException(
                    "Negative frequency");
            total += v;
        }
        double expected = (double) total / counts.length;
        if (expected < 5.0) {
            throw new IllegalArgumentException(
                    "Expected count too small for this test");
        }
        double statistic = 0.0;
        for (int v : counts) {
            double delta = v - expected;
            statistic += delta * delta / expected;
        }
        return statistic;
    }

    static boolean reject(double statistic, double cutoff) {
        return statistic > cutoff;
    }

    static void showChi(String name, int[] counts,
            double cutoff, boolean expectedReject) {
        double statistic = chiSquareUniform(counts);
        boolean actualReject = reject(statistic, cutoff);
        if (actualReject != expectedReject) {
            throw new AssertionError(
                    "Unexpected fixed-seed fixture: " + name);
        }
        System.out.printf(Locale.ROOT,
                "%s counts=%s chi2=%.3f decision=%s%n",
                name, Arrays.toString(counts), statistic,
                actualReject ? "REJECT" : "PASS");
    }

    static void swap(int[] a, int i, int j) {
        int t = a[i];
        a[i] = a[j];
        a[j] = t;
    }

    // Correct Fisher-Yates: each remaining position is chosen
    // exactly once with an appropriate uniform bound.
    static int[] fairShuffleThree(Random random) {
        int[] a = {0, 1, 2};
        for (int i = a.length - 1; i > 0; i--) {
            int j = random.nextInt(i + 1);
            swap(a, i, j);
        }
        return a;
    }

    // Deliberately biased: chooses j from the full range
    // at every i, even after earlier swaps.
    static int[] biasedShuffleThree(Random random) {
        int[] a = {0, 1, 2};
        for (int i = 0; i < a.length; i++) {
            int j = random.nextInt(a.length);
            swap(a, i, j);
        }
        return a;
    }

    // Lehmer rank of a permutation of 0..n-1.
    // The demo calls it only with valid n=3 permutations.
    static int permutationRank(int[] a) {
        int rank = 0;
        for (int i = 0; i < a.length; i++) {
            int smallerToRight = 0;
            for (int j = i + 1; j < a.length; j++) {
                if (a[j] < a[i]) smallerToRight++;
            }
            rank = rank * (a.length - i) + smallerToRight;
        }
        return rank;
    }

    static boolean isPermutationThree(int[] a) {
        if (a.length != 3) return false;
        int[] sorted = a.clone();
        Arrays.sort(sorted);
        return Arrays.equals(sorted, new int[]{0, 1, 2});
    }

    static int[] permutationHistogram(
            long seed, boolean biased) {
        int[] counts = new int[6]; // 3! = 6
        Random random = new Random(seed);
        for (int t = 0; t < TRIALS; t++) {
            int[] p = biased
                    ? biasedShuffleThree(random)
                    : fairShuffleThree(random);
            if (!isPermutationThree(p)) {
                throw new AssertionError(
                        "Shuffle did not preserve elements");
            }
            counts[permutationRank(p)]++;
        }
        return counts;
    }

    // Analytic oracle: enumerate 3^3=27 equally likely
    // random-choice paths for the deliberately broken code.
    static int[] exactBadShufflePaths() {
        int[] counts = new int[6];
        for (int j0 = 0; j0 < 3; j0++) {
            for (int j1 = 0; j1 < 3; j1++) {
                for (int j2 = 0; j2 < 3; j2++) {
                    int[] a = {0, 1, 2};
                    swap(a, 0, j0);
                    swap(a, 1, j1);
                    swap(a, 2, j2);
                    counts[permutationRank(a)]++;
                }
            }
        }
        return counts;
    }

    // Under iid uniform dice, non-overlapping pairs of
    // parity results form 4 equally likely categories.
    // Avoid overlapping pairs when calibrating with
    // the ordinary multinomial chi-square cutoff.
    static int[] parityPairs(long seed, boolean periodic) {
        int[] counts = new int[4];
        Random random = new Random(seed);
        for (int i = 0; i < TRIALS; i += 2) {
            int first = periodic
                    ? i % 6 : random.nextInt(6);
            int second = periodic
                    ? (i + 1) % 6 : random.nextInt(6);
            int category = (first & 1) * 2 + (second & 1);
            counts[category]++;
        }
        return counts;
    }

    static int[] periodicMarginal() {
        int[] counts = new int[6];
        for (int i = 0; i < TRIALS; i++) {
            counts[i % 6]++;
        }
        return counts;
    }

    // One-sample two-sided KS statistic for U[0,1].
    // A square transform is deliberately NOT uniform.
    static double ksUniform(long seed, int n,
            boolean squareValues) {
        if (n <= 0) throw new IllegalArgumentException("n<=0");
        Random random = new Random(seed);
        double[] values = new double[n];
        for (int i = 0; i < n; i++) {
            double u = random.nextDouble();
            values[i] = squareValues ? u * u : u;
        }
        Arrays.sort(values);
        double d = 0.0;
        for (int i = 0; i < n; i++) {
            double above = (i + 1.0) / n - values[i];
            double below = values[i] - (double) i / n;
            d = Math.max(d, Math.max(above, below));
        }
        return d;
    }

    static void showKs(String name, double statistic,
            double cutoff, boolean expectedReject) {
        boolean actualReject = reject(statistic, cutoff);
        if (actualReject != expectedReject) {
            throw new AssertionError(
                    "Unexpected KS fixed-seed fixture: " + name);
        }
        System.out.printf(Locale.ROOT,
                "%s D=%.5f cutoff=%.5f decision=%s%n",
                name, statistic, cutoff,
                actualReject ? "REJECT" : "PASS");
    }

    static void elementaryChecks() {
        // A validity check that BOTH samplers pass.
        Random fair = new Random(7L);
        Random biased = new Random(7L);
        for (int i = 0; i < 10_000; i++) {
            int a = fairDie(fair);
            int b = biasedDie(biased);
            if (a < 0 || a >= 6 || b < 0 || b >= 6) {
                throw new AssertionError("Range check failed");
            }
        }
        System.out.println(
                "rangeInvariant fair=true biased=true");

        Random first = new Random(99L);
        Random second = new Random(99L);
        for (int i = 0; i < 1_000; i++) {
            if (first.nextInt() != second.nextInt()) {
                throw new AssertionError(
                        "Same seed not reproducible");
            }
        }
        System.out.println("fixedSeedRepeat=PASS");

        int[] analytical = {60, 12, 12, 12, 12, 12};
        double expectedChi = 96.0;
        if (Math.abs(chiSquareUniform(analytical)
                - expectedChi) > 1e-12) {
            throw new AssertionError("Incorrect chi-square");
        }
        System.out.println("analyticChi2=96.000");
    }

    public static void main(String[] args) {
        elementaryChecks();

        showChi("dieFair",
                histogram(2026L, TRIALS, 6,
                        DistributionTestingDemo::fairDie),
                CHI6_1_PERCENT, false);
        showChi("dieBiased",
                histogram(2026L, TRIALS, 6,
                        DistributionTestingDemo::biasedDie),
                CHI6_1_PERCENT, true);

        showChi("shuffleFair",
                permutationHistogram(2027L, false),
                CHI6_1_PERCENT, false);
        showChi("shuffleBiased",
                permutationHistogram(2027L, true),
                CHI6_1_PERCENT, true);

        int[] exact = exactBadShufflePaths();
        if (!Arrays.equals(
                exact, new int[]{4, 5, 5, 5, 4, 4})) {
            throw new AssertionError(
                    "Incorrect exhaustive shuffle oracle");
        }
        System.out.println("badShuffleExactPaths="
                + Arrays.toString(exact));

        showChi("periodicMarginal",
                periodicMarginal(),
                CHI6_1_PERCENT, false);
        showChi("serialRandom",
                parityPairs(2028L, false),
                CHI4_1_PERCENT, false);
        showChi("serialPeriodic",
                parityPairs(2028L, true),
                CHI4_1_PERCENT, true);

        double cutoff = 1.63
                / Math.sqrt(CONTINUOUS_SAMPLES);
        showKs("ksUniform",
                ksUniform(2026L, CONTINUOUS_SAMPLES, false),
                cutoff, false);
        showKs("ksSquare",
                ksUniform(2026L, CONTINUOUS_SAMPLES, true),
                cutoff, true);
    }
}
~~~

### Biên dịch, chạy và kết quả dự kiến

~~~bash
javac -encoding UTF-8 DistributionTestingDemo.java
java DistributionTestingDemo
~~~

Chương trình dùng `Random` với các seed cố định, nên các tần suất sau là kết quả **cụ thể có thể tái lập** từ cùng mã và trình tự gọi tương ứng. Dòng PASS/REJECT là **quyết định của từng kiểm định**, không phải “trạng thái hoàn toàn đúng/sai của toàn bộ phần mềm”.

~~~text
rangeInvariant fair=true biased=true
fixedSeedRepeat=PASS
analyticChi2=96.000
dieFair counts=[20032, 20148, 19958, 19829, 19962, 20071] chi2=3.021 decision=PASS
dieBiased counts=[36547, 16623, 16734, 16539, 16896, 16661] chi2=16431.818 decision=REJECT
shuffleFair counts=[19948, 19873, 20196, 20268, 19763, 19952] chi2=9.377 decision=PASS
shuffleBiased counts=[17870, 22284, 21943, 22266, 17872, 17765] chi2=1409.359 decision=REJECT
badShuffleExactPaths=[4, 5, 5, 5, 4, 4]
periodicMarginal counts=[20000, 20000, 20000, 20000, 20000, 20000] chi2=0.000 decision=PASS
serialRandom counts=[14912, 14883, 15117, 15088] chi2=2.858 decision=PASS
serialPeriodic counts=[0, 60000, 0, 0] chi2=180000.000 decision=REJECT
ksUniform D=0.00520 cutoff=0.01153 decision=PASS
ksSquare D=0.24934 cutoff=0.01153 decision=REJECT
~~~

### Đọc output theo đúng nghĩa thống kê

**rangeInvariant:** ngay cả bộ sinh thiên lệch cũng trả giá trị trong 0..5; kiểm tra tính hợp lệ trên mỗi lần chạy không phát hiện lỗi phân bố.

**fixedSeedRepeat:** hai đối tượng Java Random cùng seed với cùng số thứ tự gọi tạo chuỗi như nhau. Đây là cơ chế **tái hiện**, không phải chứng minh tính độc lập ngẫu nhiên.

**analyticChi2:** sử dụng bộ đếm `[60,12,12,12,12,12]` để xác minh công thức thống kê cho đúng 96, độc lập với RNG.

**dieFair / dieBiased:** đối chiếu phân bố sáu mặt. Bộ sinh sai bị phát hiện dù mọi phần tử đều hợp lệ.

**shuffleFair / shuffleBiased:** đối chiếu phân bố của sáu hoán vị ba phần tử. Cả hai luôn tạo hoán vị hợp lệ, nhưng chỉ Fisher–Yates chuẩn có chứng minh đồng xác suất.

**badShuffleExactPaths:** liệt kê hết 27 chuỗi lựa chọn ngẫu nhiên của cách shuffle sai, cho thấy thiên lệch một cách **xác định**, không phụ thuộc seed hay thống kê.

**periodicMarginal:** một dãy hoàn toàn dự đoán được có tần suất cân bằng hoàn hảo, chi-square bằng 0; do vậy kiểm định tần suất riêng lẻ chưa đủ.

**serialRandom / serialPeriodic:** phân loại các **cặp không chồng lấn** theo chẵn/lẻ. Bộ sinh tuần hoàn có 60.000 cặp chẵn→lẻ, thống kê 180.000, trong khi mẫu PRNG tại seed minh họa không bị bác bỏ.

**ksUniform / ksSquare:** thống kê KS đo sai lệch CDF. Bình phương một số uniform tạo phân bố có CDF `√x`, thiên lệch rõ rệt dù vẫn nằm trong khoảng [0,1).

### Vì sao code không kiểm thử mọi hoán vị của m lớn?

Với m=3, `m!=6` nhóm dễ đếm. Với m=10 có `10!=3.628.800` hoán vị, với m=20 số nhóm cực lớn. Đếm mỗi hoán vị sẽ không khả thi hoặc mỗi nhóm có kỳ vọng rất nhỏ. Thay vào đó, hãy kiểm các tính chất có thể thống kê hiệu quả, ví dụ:

- Tần suất phần tử i nằm ở vị trí j.
- Phân bố vị trí đầu hoặc cuối.
- Phân bố một số mẫu hoán vị tiêu biểu.
- Tính độc lập/phụ thuộc của các lần gọi.
- Chứng minh tổ hợp thuật toán Fisher–Yates ở mức từng bước.

Cần nhớ: các thống kê rút gọn có thể **bỏ sót một số kiểu thiên lệch**, nên chúng là bộ cảm biến bổ sung, không thay thế chứng minh phân bố đều.

## 12. Chi phí tính toán và giới hạn

### Histogram rời rạc

Với N mẫu và k loại:

- **Thời gian:** O(N+k), chưa kể chi phí tạo mỗi mẫu.
- **Bộ nhớ:** O(k).
- **Thống kê chi-square:** O(k) sau khi đếm.

### Phân bố hoán vị

Nếu shuffle m phần tử mất O(m), N lần thử tốn O(Nm). Đếm trực tiếp mọi hoán vị cần O(m!) bộ nhớ và chỉ phù hợp với **m rất nhỏ**. Mã minh họa dùng m=3, nên thời gian tổng thể O(N) theo N.

### Kiểm tra cặp chẵn/lẻ

N lượt được tổ hợp thành N/2 cặp không chồng lấn; dùng bốn bộ đếm và O(N) thời gian, O(1) bộ nhớ phụ. Việc cố ý không chồng lấn là để không đưa thêm phụ thuộc do **cách nhóm dữ liệu**, khi muốn sử dụng ngưỡng chi-square multinomial đơn giản.

### KS cho N mẫu liên tục

Phải sắp xếp N giá trị:

- **Thời gian:** O(N log N) vì sort (sau O(N) lần sinh mẫu).
- **Bộ nhớ:** O(N) để giữ dãy trước khi sort, chưa kể chi phí bộ nhớ nội bộ của thuật toán sort.

Đối với dữ liệu streaming cực lớn, có thể dùng histogram/quantile sketch hoặc thuật toán xấp xỉ CDF khác; nhưng phải định nghĩa rõ sai số và cách hiệu chỉnh ngưỡng, không gọi mọi xấp xỉ là kiểm định KS exact.

### Các vấn đề kỹ thuật

- Nếu N quá lớn, bộ đếm `int` có thể tràn; dùng `long` cho số đếm khi cần trên 2³¹−1.
- Khi tính χ², chuyển sang `double` trước phép chia để tránh mất phần thập phân do chia nguyên.
- Không dùng `random.nextInt() % 6` một cách tùy tiện: phép dư với số âm trong Java có thể âm, và ánh xạ modulo không được xử lý cẩn thận có thể tạo thiên lệch. Dùng `nextInt(6)`.
- Không dùng `Math.abs(random.nextInt())` để tạo số không âm vì `Math.abs(Integer.MIN_VALUE)` vẫn âm.
- Nếu thay bộ sinh bằng `SecureRandom` trong yêu cầu bảo mật, cần thêm đánh giá chất lượng/nguồn entropy theo tiêu chuẩn chuyên biệt; PASS các phép chi-square/KS không là bằng chứng mật mã.

## 13. Khi phân bố mục tiêu không đồng đều

Không phải thuật toán ngẫu nhiên nào cũng cần tạo **uniform distribution**. Ví dụ chọn hạng mục theo trọng số:

`p=[0.1,0.2,0.7]`.

Khi đó dùng kỳ vọng:

`E_i=N p_i`,

và thống kê:

`χ²=Σ_i (O_i−Np_i)²/(Np_i)`.

**Không** đem thuật toán phân bố [0.1,0.2,0.7] đi so với xác suất đồng đều 1/3, rồi kết luận nó sai vì bị bác bỏ. Phân bố tham chiếu phải xuất phát từ **đặc tả**.

Các tình huống mở rộng:

- **Reservoir sampling k phần tử từ n phần tử:** mỗi phần tử có xác suất xuất hiện `k/n` khi yêu cầu chọn đều tập con không hoàn lại. Vì các sự kiện “phần tử i được chọn” phụ thuộc nhau (một lần chọn có đúng k phần tử), không dùng mô hình multinomial đơn giản cho các tần suất inclusion như thể chỉ có một loại kết quả mỗi trial. Có thể liệt kê mọi tập con `C(n,k)` khi n nhỏ hoặc dùng công thức kiểm định phù hợp.
- **Randomized quicksort:** kiểm tra đầu ra sắp xếp phải đúng **trên từng lượt**; kiểm tra phân bố số phép so sánh/thời gian có thể hỗ trợ phát hiện pivot bias nhưng không chứng minh độ phức tạp kỳ vọng cho mọi đầu vào.
- **Thuật toán Monte Carlo có xác suất sai:** thiết kế test cho **tỉ lệ thất bại** trên một lớp đầu vào xác định; một lần thành công không xác nhận mức bảo đảm như 99%.
- **Thuật toán Las Vegas:** đầu ra phải đúng trên mọi lần kết thúc; biến ngẫu nhiên thường là **thời gian chạy**, nên cần kiểm tra phân bố runtime/tail và chi phí kỳ vọng, bên cạnh bất biến tính đúng.
- **Mô phỏng phân bố chuẩn hoặc Poisson:** dùng phân bố tham chiếu đúng với các tham số của bài, phép kiểm và hiệu chỉnh phù hợp; không dùng KS continuous standard trên dữ liệu Poisson rời rạc mà không thay đổi cách hiệu chỉnh.

## 14. Phân tích một lần REJECT đúng cách

Khi test phân bố báo REJECT, nên:

1. **Lưu seed, N, mã nguồn, thống kê, cutoff, phiên bản JDK, hệ điều kiện chạy.**
2. Xem kỹ H₀ và cách gán mẫu vào nhóm: có đúng đặc tả không?
3. Kiểm tra từng mẫu có hợp lệ và bộ đếm có bị tràn/nhầm chỉ số không.
4. Xác định mẫu có độc lập theo thiết kế không, hoặc thuật toán có state giữa các lượt hay không.
5. Tách hàm ánh xạ từ RNG sang kết quả và kiểm tra logic: biên của `nextInt`, modulo bias, giới hạn vòng lặp shuffle, chia trọng số.
6. Kiểm tra các phép kiểm khác có bổ sung bằng chứng không: marginal, serial, chi-square, KS, phân tích tổ hợp.
7. Kiểm tra **mức ý nghĩa và số lượng phép kiểm**; một REJECT từ một test hợp lệ vẫn có thể là sai dương, nhất là khi thử nhiều test.
8. Tìm **phản ví dụ nhỏ có thể chứng minh**, như 27 đường lựa chọn của shuffle sai.
9. Khi sửa, giữ regression test phát hiện lỗi đó và kiểm tra lại phân bố bằng thiết kế trước, tránh xoay vòng seed cho tới khi PASS.
10. Báo cáo trung thực: “bác bỏ ở α=1% dưới giả thiết iid”, “không bác bỏ”, hay “chưa thể hiệu chỉnh kiểm định”, không dùng kết luận cực đoan “chắc chắn ngẫu nhiên hoàn hảo”.

### Một cách tổ chức kiểm thử tự động tốt

- **Unit tests không xác suất:** giá trị nằm trong miền; hoán vị không thiếu/thừa phần tử; đáp ứng ràng buộc; seed được truyền đúng; oracle tổ hợp nhỏ.
- **Statistical regression tests:** test với seed/cỡ mẫu/cutoff đăng ký cố định, ghi thống kê và hạn chế false alarms.
- **Kiểm thử chất lượng sâu hơn:** chạy thêm nhiều bộ seed với kế hoạch thống kê và điều chỉnh mức α, kiểm tra các mô hình phụ thuộc, phân bố tail và chất lượng entropy nếu thật sự cần.
- **Chứng minh:** với những thuật toán có cấu trúc rõ như Fisher–Yates, dùng chứng minh xác suất 1/m! làm căn cứ chính.

## 15. Lỗi thường gặp

1. Chỉ chạy một lần rồi tuyên bố bộ sinh ngẫu nhiên đúng.
2. Chỉ kiểm tra range 0..k−1, không kiểm tra phân bố.
3. Chỉ kiểm tra kết quả shuffle là hoán vị, không kiểm tra tính đồng xác suất.
4. Dùng thuật toán xáo trộn chọn j trong [0,m−1] ở mọi vòng và nghĩ giống Fisher–Yates.
5. Không xác định H₀ trước khi thu thập mẫu.
6. Dùng thống kê uniform cho bộ sinh có xác suất mục tiêu **không đều**.
7. So chênh lệch tần suất bằng ngưỡng tùy ý không xét N.
8. Quên χ² phải chia bình phương sai lệch cho số kỳ vọng Eᵢ.
9. Tính chia bằng số nguyên và làm mất phần thập phân.
10. Áp xấp xỉ χ² khi Eᵢ rất nhỏ mà không hiệu chỉnh.
11. Dùng df=k−1 khi tham số đã được ước lượng từ cùng mẫu mà chưa điều chỉnh.
12. Không kiểm tra giả thiết mẫu độc lập.
13. Đem các cặp **chồng lấn** vào kiểm định multinomial iid mà không hiệu chỉnh.
14. Thấy các tần suất từng mặt đều rồi kết luận chuỗi độc lập.
15. Chỉ test parity hoặc một đại lượng rút gọn, bỏ sót thiên lệch khác.
16. Đếm mọi hoán vị của m lớn, khiến m! bùng nổ.
17. Không biết KS một mẫu chuẩn áp dụng cho phân bố tham chiếu liên tục.
18. Áp cùng KS cutoff cho dữ liệu rời rạc nhiều ties mà không hiệu chỉnh.
19. Dùng tham số ước lượng từ mẫu rồi so với ngưỡng KS chuẩn.
20. Nhầm p-value với xác suất H₀ đúng.
21. Nhầm không bác bỏ H₀ với chứng minh H₀ đúng.
22. Nhầm một lần bác bỏ H₀ với chứng minh chắc chắn có bug.
23. Không tính đến false-positive rate khi có nhiều phép kiểm.
24. Chạy nhiều seed rồi **chỉ giữ seed PASS**.
25. Khởi tạo lại RNG cùng seed **bên trong mỗi lượt**, tạo chuỗi lặp kết quả đầu.
26. Không ghi seed khi một test ngẫu nhiên thất bại.
27. Dùng `Random` như một nguồn bảo mật mật mã.
28. Dùng modulo với số ngẫu nhiên âm rồi gây kết quả sai phạm vi.
29. Dùng `Math.abs(Integer.MIN_VALUE)` mà không biết nó vẫn âm.
30. Bỏ giả thiết về số lượng mẫu và hiệu ứng cần phát hiện khi chọn N.
31. Gọi kiểm định tần suất là kiểm định độc lập toàn bộ.
32. Dùng seed cố định trong regression rồi coi một lần PASS là bằng chứng tổng quát.
33. Không kết hợp kiểm thử thống kê với test chức năng từng mẫu.
34. Dùng kiểm thử ngẫu nhiên thay cho chứng minh thuật toán khi có thể chứng minh chính xác.
35. Không phân biệt “phân bố đúng” với “kết quả tốt cho mỗi đầu vào” của thuật toán random.
36. Không báo điều kiện thống kê và giới hạn khi công bố PASS/REJECT.

## 16. Bài tập có lời giải

**Bài 1.** Một xúc xắc luôn trả số trong 0..5 có chắc đều không? **Đáp án:** không; kiểm tra range không kiểm tra xác suất.

**Bài 2.** Đầu ra `[0,1,2]` sau shuffle hợp lệ có chứng minh shuffle đều không? **Đáp án:** không; một hoán vị hợp lệ có thể bị ưu tiên.

**Bài 3.** H₀ khi kiểm tra xúc xắc đều là gì? **Đáp án:** `P(X=i)=1/6` với mọi i=0..5.

**Bài 4.** N=120000 và k=6, số đếm kỳ vọng mỗi mặt? **Đáp án:** 20000.

**Bài 5.** Công thức Pearson chi-square? **Đáp án:** `Σ(Oᵢ−Eᵢ)²/Eᵢ`.

**Bài 6.** Với sáu nhóm, bậc tự do thông thường khi xác suất đã biết? **Đáp án:** k−1=5.

**Bài 7.** Với `counts=[20,20,20,20,20,20]`, chi-square? **Đáp án:** 0.

**Bài 8.** Với `counts=[60,12,12,12,12,12]`, chi-square? **Đáp án:** 96.

**Bài 9.** Chi-square=96 có vượt ngưỡng 15.086? **Đáp án:** có, bác bỏ H₀ ở α=1% theo giả thiết kiểm định.

**Bài 10.** PASS tại mức α=1% có chứng minh bộ sinh hoàn toàn đều? **Đáp án:** không, chỉ là chưa bác bỏ H₀.

**Bài 11.** Nguy cơ false positive là gì? **Đáp án:** bác bỏ H₀ dù H₀ thật, với xác suất xấp xỉ mức ý nghĩa khi giả thiết đúng.

**Bài 12.** Vì sao tăng N giúp phát hiện bias nhỏ? **Đáp án:** SE của tỉ lệ giảm theo `1/√N`, nên cùng độ lệch thật dễ phân biệt khỏi nhiễu hơn.

**Bài 13.** Công thức Fisher–Yates chọn j trong khoảng nào tại i? **Đáp án:** số nguyên đều trong [0,i].

**Bài 14.** Với m phần tử phân biệt, xác suất mỗi hoán vị dưới Fisher–Yates chuẩn? **Đáp án:** `1/m!`.

**Bài 15.** Với m=3, có bao nhiêu hoán vị? **Đáp án:** 3!=6.

**Bài 16.** Với m=3, thuật toán shuffle sai chọn j trong [0,2] ở cả ba lượt có bao nhiêu đường lựa chọn? **Đáp án:** 3³=27.

**Bài 17.** Vì sao 27 đường đồng xác suất không thể phân đều vào sáu hoán vị bằng cùng số đường nguyên? **Đáp án:** 27/6=4.5 không nguyên; đây là dấu hiệu của thiên lệch nếu mỗi đường dẫn tới đúng một hoán vị.

**Bài 18.** Phân bố chính xác của shuffle sai n=3 theo rank 0..5? **Đáp án:** số đường `[4,5,5,5,4,4]` trên 27.

**Bài 19.** Một dãy 0..5 lặp tuần hoàn có tần suất biên như thế nào khi N chia hết cho 6? **Đáp án:** hoàn toàn đều.

**Bài 20.** Dãy tuần hoàn ấy có độc lập theo thời gian không? **Đáp án:** không; lượt kế tiếp xác định từ lượt trước.

**Bài 21.** Với 120000 lượt, tạo cặp không chồng lấn được bao nhiêu cặp? **Đáp án:** 60000.

**Bài 22.** Với parity độc lập đều, bốn loại EE,EO,OE,OO có xác suất gì? **Đáp án:** mỗi loại 1/4.

**Bài 23.** Vì sao không dùng trực tiếp cặp chồng lấn với cutoff multinomial iid? **Đáp án:** các cặp chia sẻ quan sát, không độc lập như giả thiết để hiệu chỉnh ngưỡng đơn giản.

**Bài 24.** KS so sánh đối tượng nào? **Đáp án:** hàm phân phối thực nghiệm với CDF lý thuyết.

**Bài 25.** Với U đều [0,1), V=U² có CDF nào trên [0,1]? **Đáp án:** `F_V(v)=√v`.

**Bài 26.** V có còn nằm trong [0,1) không? **Đáp án:** có, nhưng không còn phân bố đều.

**Bài 27.** Hiệu lớn nhất của `√v−v` trên [0,1]? **Đáp án:** 1/4 tại v=1/4.

**Bài 28.** Ngưỡng KS xấp xỉ 1% với N=20000? **Đáp án:** `1.63/√20000≈0.01153`.

**Bài 29.** Vì sao seed cố định hữu ích? **Đáp án:** tái hiện chuỗi gọi PRNG và lỗi trong kiểm thử hồi quy.

**Bài 30.** Vì sao không nên khởi tạo RNG cùng seed ở mỗi lần lấy mẫu? **Đáp án:** lặp lại phần tử đầu của cùng chuỗi, phá mô hình phân bố độc lập mong muốn.

**Bài 31.** Mười kiểm định độc lập, mỗi phép có α=1%, xác suất có ít nhất một sai dương? **Đáp án:** `1−0.99¹⁰≈9.56%`.

**Bài 32.** Bonferroni dùng ngưỡng gì khi có m test để kiểm soát family-wise error ≤α? **Đáp án:** α/m cho mỗi test.

**Bài 33.** Với lựa chọn có trọng số p=[0.1,0.2,0.7], phải so với kỳ vọng nào? **Đáp án:** `[0.1N,0.2N,0.7N]`, không phải N/3 mỗi nhóm.

**Bài 34.** Với reservoir sampling k trong n phần tử, xác suất một phần tử được chọn dưới lấy mẫu đều là bao nhiêu? **Đáp án:** k/n.

**Bài 35.** Kiểm tra chi-square pass có xác minh RNG bảo mật không? **Đáp án:** không; các tính chất mật mã cần tiêu chuẩn/giả thiết khác, và `Random` không phải PRNG mật mã.

**Bài 36.** Trong một dự án thật, khi thống kê REJECT nên làm gì đầu tiên? **Đáp án:** lưu seed, dữ liệu, ngưỡng, N và kiểm tra lại giả thiết H₀/độc lập trước khi sửa code hoặc thay seed.

## 17. Checklist cuối bài

1. Đã ghi rõ đại lượng nào được yêu cầu ngẫu nhiên, theo **phân bố nào** chưa?
2. Đã kiểm tra bất biến từng đầu ra **riêng với phân bố** chưa?
3. H₀ và H₁ có được nêu trước khi chạy thống kê không?
4. Đã chọn α, N, seed và cách nhóm trước khi thấy kết quả chưa?
5. Số lần kỳ vọng mỗi nhóm có đủ để dùng chi-square xấp xỉ không?
6. Đã chọn đúng bậc tự do cho mô hình tham chiếu chưa?
7. Các lần thử có đáp ứng giả thiết độc lập/đồng phân bố của kiểm định không?
8. Nếu kiểm serial, có tránh dùng cặp chồng lấn dưới mô hình iid multinomial đơn giản không?
9. Nếu kiểm shuffle m nhỏ, có đếm đủ m! hoán vị và đối chiếu tổ hợp chính xác khi có thể không?
10. Nếu m lớn, có chọn thống kê cấu trúc không làm bùng nổ m! bộ đếm không?
11. Có kết hợp test phân bố biên với kiểm phụ thuộc theo thời gian khi cần không?
12. Nếu dữ liệu liên tục, đã chọn một kiểm định phù hợp như KS và biết các điều kiện hiệu chỉnh không?
13. Nếu phân bố không đều, đã dùng kỳ vọng `Npᵢ` đúng đặc tả không?
14. Đã phân biệt “không bác bỏ H₀” và “chứng minh H₀ đúng” chưa?
15. Đã tính đến sai dương do nhiều phép kiểm và nguy cơ p-hacking chưa?
16. Có chọn N dựa trên effect size muốn phát hiện, không chỉ dựa trên tiện chạy không?
17. Có lưu seed, số mẫu, thống kê, cutoff, phiên bản chương trình để tái hiện không?
18. Có tránh tạo lại RNG cùng seed trong mỗi trial không?
19. Đã tránh `nextInt()%bound`/`Math.abs(Integer.MIN_VALUE)` khi sinh số bị chặn không?
20. Có phân biệt PRNG mô phỏng với RNG bảo mật và tiêu chuẩn chứng nhận tương ứng không?
21. Khi test REJECT, có dùng oracle độc lập/giải thích tổ hợp để điều tra không?
22. Với bài Monte Carlo/Las Vegas, đã kiểm đúng đại lượng xác suất thất bại/thời gian chạy, thay vì chỉ kiểm phân bố uniform không liên quan không?

**Ghi nhớ:** một lần chạy đúng không đủ cho thuật toán ngẫu nhiên hóa. Hãy kiểm **tính hợp lệ**, **phân bố mong muốn** và **mức phụ thuộc** bằng các phép thử phù hợp với giả thiết, số mẫu và độ nhạy. Dùng **seed cố định** để tái hiện, nhưng không chọn seed sau khi xem PASS/REJECT. Một kiểm định PASS chỉ có nghĩa **chưa có bằng chứng thống kê đủ mạnh để bác bỏ giả thuyết**; khi có thể chứng minh thuật toán như Fisher–Yates bằng lập luận xác suất chính xác, hãy dùng chứng minh làm nền tảng và kiểm thử phân bố làm công cụ phát hiện lỗi triển khai.
