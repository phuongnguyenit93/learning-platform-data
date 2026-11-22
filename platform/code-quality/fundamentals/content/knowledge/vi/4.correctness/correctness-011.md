# Giới hạn của suy luận, kiểm thử và phân tích tự động

Trong chương **Tính đúng đắn** của module **CODE_QUALITY_FUNDAMENTALS**, ta đang tìm hiểu điều gì khiến mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Khi đánh giá tính đúng đắn, ba nguồn bằng chứng thường gặp là **suy luận về chương trình**, **kiểm thử** và **phân tích tự động**. Mỗi cách giúp phát hiện một nhóm sai sót, nhưng cũng có những giả định và giới hạn riêng.

Một chương trình vượt qua tất cả bài test vẫn có thể sai ở đầu vào chưa được kiểm tra. Một đoạn mã có vẻ hợp lý khi đọc vẫn có thể lỗi vì tràn số, thực thi đồng thời hoặc một chi tiết trong yêu cầu chưa được làm rõ. Một công cụ phân tích báo “không tìm thấy vấn đề” cũng chỉ có thể kết luận trong **phạm vi thuộc tính và mô hình mà nó thực sự kiểm tra**.

Bài học này hướng dẫn cách kết hợp các nguồn bằng chứng để ra quyết định kỹ thuật, đồng thời tránh nhầm lẫn giữa **“chưa tìm thấy lỗi”** và **“đã chứng minh không có lỗi”**.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Nêu rõ tính đúng đắn của chương trình luôn gắn với yêu cầu, tiền điều kiện và môi trường thực thi.
2. Phân biệt điều một lập luận, một bài kiểm thử và một công cụ phân tích có thể xác lập.
3. Giải thích các giới hạn như tập đầu vào quá lớn, bài toán *test oracle*, tràn số, đường thực thi bùng nổ và sự khác biệt giữa mô hình với hệ thống thực.
4. Đọc kết quả *coverage*, phân tích tĩnh, kiểm thử dựa trên thuộc tính và kiểm thử đột biến một cách đúng mức.
5. Chọn nhiều loại bằng chứng cho một yêu cầu quan trọng, đặc biệt khi mã Java có tính toán số học, truy cập cơ sở dữ liệu hoặc xử lý đồng thời.
6. Ghi lại giả định và phạm vi kiểm chứng để người khác có thể đánh giá và bảo trì mã an toàn.

## 2. Trước tiên, “đúng” nghĩa là gì?

Tính đúng đắn không tồn tại độc lập với một **đặc tả**. Muốn kết luận hàm đúng, cần ít nhất trả lời:

- **Đầu vào hợp lệ:** những giá trị và trạng thái nào được phép xuất hiện?
- **Đầu ra và tác dụng phụ:** hàm phải trả gì, ghi gì hoặc phát sự kiện nào?
- **Tình huống biên:** đúng ngưỡng, bằng 0, rỗng, thời gian hết hạn hoặc vượt giới hạn được xử lý thế nào?
- **Điều kiện môi trường:** có thể bị gọi đồng thời không, dữ liệu có thể đổi giữa hai thao tác không, phụ thuộc ngoài có thể lỗi không?
- **Phạm vi được yêu cầu:** đang xác minh một phép tính, một giao dịch, một API hay toàn bộ hành trình người dùng?

Ví dụ, yêu cầu “không cho phép giao dịch vượt hạn mức” vẫn chưa đủ rõ. Hạn mức áp dụng cho mỗi giao dịch hay tổng trong ngày? Tính theo múi giờ nào? Các giao dịch đang chờ có chiếm hạn mức không? Khi có hai yêu cầu đến cùng lúc thì kết quả phải thế nào?

Nếu đặc tả mơ hồ hoặc sai so với nhu cầu thực tế, chương trình có thể **đúng theo đặc tả đang dùng** nhưng vẫn không đáp ứng yêu cầu của sản phẩm. Điều này cũng giải thích vì sao kiểm tra tính đúng đắn theo đặc tả (*verification*) và xem sản phẩm có giải quyết đúng nhu cầu (*validation*) là hai câu hỏi liên quan nhưng khác nhau.

### 2.1. Phân biệt một số mức độ phát biểu

| Phát biểu | Có thể kết luận gì? | Không thể suy ra ngay điều gì? |
| --- | --- | --- |
| “Tôi đọc mã và thấy hợp lý.” | Đã có một lượt xem xét logic, có thể phát hiện một số thiếu sót. | Mọi đầu vào và trạng thái đều đúng. |
| “10.000 bài test đều đỗ.” | Những lần chạy đó khớp với kết quả mong đợi đã kiểm tra. | Không tồn tại ca sai khác ở những trường hợp chưa chạy. |
| “Coverage đạt 100% dòng lệnh.” | Mọi dòng được công cụ đo ghi nhận là đã thực thi trong lần chạy test. | Assertion đủ mạnh hoặc mọi nhánh, mọi giá trị đều đúng. |
| “Static analyzer không báo lỗi.” | Công cụ không phát hiện cảnh báo thuộc phạm vi phân tích và cấu hình hiện tại. | Mã hoàn toàn không có lỗi. |
| “Đã chứng minh thuộc tính P dưới giả định A.” | Nếu mô hình, quy tắc suy luận và các giả định A được đáp ứng, P theo đó được bảo đảm. | P vẫn đúng nếu bỏ giả định hoặc thay đổi phạm vi hệ thống. |

Một kết luận kỹ thuật đáng tin cần nói rõ **đối tượng, thuộc tính, điều kiện và bằng chứng**.

## 3. Suy luận về chương trình: mạnh ở chỗ nào, giới hạn ở đâu?

**Suy luận** là dùng logic, hiểu biết về ngôn ngữ lập trình và các điều kiện đã biết để giải thích vì sao chương trình phải hoặc không thể tạo ra một kết quả. Suy luận có thể không chính thức (review, diễn giải bất biến) hoặc chính thức hơn (đặc tả và chứng minh bằng hệ thống logic).

### 3.1. Tiền điều kiện, hậu điều kiện và bất biến

Xét một hàm chỉ nhận số tiền không âm. Ta có thể mô tả:

- **Tiền điều kiện (precondition):** `amount >= 0`.
- **Hậu điều kiện (postcondition):** kết quả không âm và không vượt một giới hạn đã định.
- **Bất biến (invariant):** tổng đã sử dụng không vượt hạn mức sau mọi lần cập nhật hợp lệ.

Trong logic Hoare, một cách trình bày rút gọn là:

`{P} C {Q}`

Ở đây, `P` là tiền điều kiện, `C` là đoạn chương trình, `Q` là hậu điều kiện. Cách viết này thường mô tả **tính đúng đắn bộ phận**: nếu `P` đúng và `C` kết thúc, `Q` đúng. Muốn chứng minh **tính đúng đắn toàn phần**, còn phải lập luận về khả năng kết thúc. Với đoạn mã gọi API, đọc luồng vô hạn hoặc chờ khóa, đây có thể là vấn đề không đơn giản.

Trong thực hành Java, việc nêu được bất biến bằng ngôn ngữ đời thường đã rất hữu ích:

> “Sau mỗi giao dịch được chấp nhận, tổng tiền trong ngày luôn không âm và không lớn hơn hạn mức.”

Câu này cho người review một điều kiện cần bảo vệ, từ đó suy ra các phép kiểm tra dữ liệu và các ca test có giá trị.

### 3.2. Suy luận phải dựa trên giả định chính xác

Một lập luận về số học nguyên toán học có thể sai khi áp vào `int` hoặc `long` trong Java vì số nguyên máy có miền hữu hạn. Ví dụ:

~~~java
long used = Long.MAX_VALUE - 5;
long incoming = 10;
long limit = Long.MAX_VALUE;

boolean allowed = used + incoming <= limit;
System.out.println(allowed); // true do long bị tràn số
~~~

Về số học thông thường, tổng lớn hơn `Long.MAX_VALUE`, nên không thể được chấp nhận. Nhưng phép cộng hai giá trị `long` vượt miền biểu diễn và cho ra giá trị âm do tràn số, khiến so sánh trả về `true`. Java không tự ném ngoại lệ cho phép cộng `long` thông thường khi tràn.

Nếu người review chỉ áp dụng quy tắc số học thực “thêm tiền thì tổng tăng”, lập luận ấy thiếu giả định quan trọng về **miền giá trị và ngữ nghĩa máy**.

### 3.3. Đọc mã và chứng minh không phải một hoạt động duy nhất

Review mã có thể phát hiện lỗi logic, trường hợp biên, xử lý ngoại lệ bất nhất và đoạn mã khó hiểu. Nhưng người review thường không duyệt hết mọi đường đi thực thi. Khi số nhánh và trạng thái tăng, khả năng bỏ sót cũng tăng.

Chứng minh hình thức có thể mạnh hơn cho **thuộc tính được mô hình hóa rõ**, nhưng vẫn phải tin vào:

- Đặc tả thực sự diễn đạt đúng hành vi cần có.
- Các tiền điều kiện và giả định môi trường là đúng.
- Mô hình của thư viện, runtime, luồng và I/O đủ sát thực tế.
- Phạm vi kết luận có bao gồm mã chạy và cách triển khai thực tế hay không.

Một chứng minh đúng về hàm tính toán đơn lẻ không tự chứng minh toàn bộ giao dịch database dùng hàm ấy cũng đúng.

### 3.4. Giới hạn cơ bản của phân tích tổng quát

Đối với chương trình đủ tổng quát, không tồn tại một thuật toán luôn kết thúc và quyết định chính xác mọi thuộc tính hành vi tùy ý cho mọi chương trình. **Bài toán dừng** là ví dụ kinh điển: không thể xây dựng một bộ quyết định tổng quát trả lời đúng liệu mọi chương trình có dừng trên đầu vào đã cho hay không.

Điều này **không có nghĩa** ta không thể chứng minh bất kỳ chương trình nào, hay mọi phân tích tự động đều vô ích. Với một miền hữu hạn, một ngôn ngữ bị giới hạn hoặc một thuộc tính cụ thể, vẫn có thể kiểm tra hoặc chứng minh đầy đủ. Giới hạn xuất hiện khi đòi một công cụ hoàn hảo cho **mọi chương trình và mọi hành vi**.

## 4. Kiểm thử: bằng chứng thực thi cụ thể và những khoảng trống

**Kiểm thử** chạy chương trình trên những tình huống được chọn rồi so sánh hành vi quan sát được với **kỳ vọng**. Một bài test thất bại hợp lệ có thể chỉ ra sai lệch cụ thể; một bài test thành công cho biết điều kiện đã kiểm tra chưa phát hiện sai lệch.

### 4.1. Không gian trạng thái thường lớn hơn số lần test

Ngay cả một hàm nhận hai giá trị `int` cũng có số cặp đầu vào rất lớn. Với hệ thống thực, kết quả còn phụ thuộc vào trạng thái database, thời gian, thứ tự luồng, mạng, cấu hình và phiên bản dịch vụ bên ngoài.

Kiểm thử thường phải chọn đại diện bằng các kỹ thuật như:

- **Phân lớp tương đương:** chọn trường hợp tiêu biểu của những nhóm đầu vào được dự đoán có hành vi giống nhau.
- **Phân tích giá trị biên:** kiểm tra tại ngưỡng, sát dưới và sát trên ngưỡng.
- **Kiểm thử theo bảng quyết định:** tổ hợp các điều kiện nghiệp vụ có ảnh hưởng đến kết quả.
- **Kiểm thử chuyển trạng thái:** trạng thái trước, sự kiện xảy ra và trạng thái sau.
- **Kiểm thử hồi quy:** giữ những tình huống từng gây lỗi để phát hiện lỗi tái xuất hiện.

Các kỹ thuật này làm việc chọn test có hệ thống hơn, nhưng độ tin cậy phụ thuộc vào **giả định về các nhóm tương đương** và **độ đầy đủ của những quy tắc đã biết**.

### 4.2. Bài toán test oracle

*Test oracle* là cơ chế xác định **kết quả đúng phải là gì**. Nếu oracle sai, test có thể đỗ trong khi chương trình sai theo nhu cầu thực.

Ví dụ:

~~~java
int actualFee = shippingFee(500_000);
assertEquals(30_000, actualFee);
~~~

Nếu yêu cầu thật sự là “miễn phí khi tổng tiền từ 500.000 trở lên”, assertion trên đang củng cố một lỗi. Việc chạy test tự động không giúp phát hiện sai lệch giữa test và đặc tả. Khi đó cần xem lại tiêu chí chấp nhận với người chịu trách nhiệm nghiệp vụ.

Với những hệ thống mà kết quả chính xác khó dự đoán (thuật toán tối ưu, mô phỏng, xử lý dữ liệu lớn), có thể kiểm tra **thuộc tính** hoặc **quan hệ giữa nhiều lần chạy**, chẳng hạn “thêm một mục có giá dương không làm giảm tổng tiền trước chiết khấu”. Tuy nhiên, các thuộc tính này cũng phải được xác định đúng và chưa chắc bao phủ toàn bộ yêu cầu.

### 4.3. Coverage nói về thực thi, không phải tính đúng đắn

Xem xét ví dụ:

~~~java
int absolute(int x) {
    return x < 0 ? -x : x;
}
~~~

Một bài test với `x = -1` và một bài test với `x = 1` có thể bao phủ cả hai nhánh, nhưng vẫn bỏ sót `Integer.MIN_VALUE`. Trong Java, giá trị dương của `Integer.MIN_VALUE` không biểu diễn được bằng `int`; phép đổi dấu bằng dấu trừ thông thường sẽ bị tràn số và cho ra giá trị âm.

Độ bao phủ dòng, nhánh hoặc điều kiện là các thước đo hữu ích nhưng không thay thế cho **độ mạnh của assertion** và **lựa chọn đầu vào có ý nghĩa**. Coverage 100% không bảo đảm mọi trường hợp đúng; coverage thấp có thể cho biết có vùng mã chưa được chạy nhưng không trực tiếp nói vùng đó có lỗi.

### 4.4. Property-based testing, fuzzing và mutation testing

| Kỹ thuật | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| **Property-based testing** | Sinh nhiều dữ liệu theo ràng buộc; kiểm tra tính chất tổng quát thay vì liệt kê toàn bộ ví dụ. | Thuộc tính có thể thiếu, bộ sinh có thể không chạm đến trạng thái nguy hiểm. |
| **Fuzzing** | Đưa đầu vào bất thường, ngẫu nhiên hoặc dựa trên độ bao phủ để tìm lỗi xử lý dữ liệu, crash, vi phạm bất biến. | Không tự xác lập mọi hành vi nghiệp vụ là đúng; kết quả phụ thuộc bộ tạo dữ liệu và oracle. |
| **Mutation testing** | Thử thay đổi mã có chủ đích để xem test có phát hiện thay đổi hành vi. | Mutant tương đương về hành vi có thể không bị “giết”; điểm số không đồng nghĩa chứng minh đúng. |
| **Kiểm thử tích hợp / end-to-end** | Kiểm tra tương tác nhiều thành phần và luồng vận hành gần thực tế hơn. | Chi phí lớn hơn, môi trường khó kiểm soát và vẫn không bao phủ mọi tình huống. |

Kết quả hữu ích nhất khi nhóm hiểu được câu hỏi mà mỗi kỹ thuật trả lời, thay vì đặt mục tiêu duy nhất là “nâng mọi chỉ số lên 100%”.

### 4.5. Test ổn định vẫn có thể bỏ sót lỗi đồng thời

Một hàm có thể vượt qua toàn bộ unit test chạy tuần tự nhưng thất bại khi hai yêu cầu thao tác cùng dữ liệu đồng thời. Test riêng lẻ không chứng minh tính nguyên tử của một giao dịch; ngay cả kiểm thử nhiều luồng cũng chỉ thử những lịch thực thi đã xảy ra.

Tương tự, mock có thể giúp cô lập logic, nhưng mock trả dữ liệu quá lý tưởng có thể che giấu việc API thật trả lỗi, timeout hoặc dữ liệu sai định dạng.

## 5. Phân tích tự động: công cụ kiểm tra đúng phần nó mô hình hóa

**Phân tích tự động** có thể diễn ra **không chạy chương trình** (phân tích tĩnh) hoặc trong/qua các lần chạy (phân tích động). Trong ngữ cảnh này, ta tập trung vào những công cụ giúp phát hiện lỗi hoặc hỗ trợ kiểm chứng ngoài việc tự viết ca test thông thường.

### 5.1. Trình biên dịch và hệ thống kiểu

Trình biên dịch Java phát hiện nhiều lỗi cú pháp, sai kiểu và vi phạm quy tắc ngôn ngữ ngay trước khi chương trình chạy. Đây là dạng bằng chứng mạnh trong **phạm vi hệ thống kiểu của Java**.

Ví dụ, gán trực tiếp một `String` cho biến `int` sẽ không biên dịch. Nhưng mã Java biên dịch hợp lệ vẫn có thể:

- Sai công thức chiết khấu hoặc tính thuế.
- Tràn số học `int` hoặc `long`.
- Truy cập `null` gây `NullPointerException` trong một số đường đi.
- Có lỗi race condition giữa các luồng.
- Không đáp ứng yêu cầu về phân quyền, hiệu năng hoặc tính nhất quán dữ liệu.

**Biên dịch thành công là điều kiện quan trọng, nhưng không đồng nghĩa chương trình đúng theo nghiệp vụ.**

### 5.2. Phân tích tĩnh và cảnh báo

Một công cụ phân tích tĩnh có thể tìm mẫu nguy hiểm như:

- Tài nguyên mở mà không đóng theo một đường đi được phân tích.
- Giá trị có thể null rồi bị dereference.
- Tham số chưa được kiểm tra.
- Một số đường đi không thể đạt tới hoặc điều kiện bất khả thi.
- Dấu hiệu dùng API bảo mật, dữ liệu hoặc đồng thời thiếu an toàn.

Tuy vậy, một cảnh báo là **một phát hiện cần giải thích theo ngữ cảnh**, không phải lúc nào cũng là lỗi thực tế. Không có cảnh báo cũng không có nghĩa là mọi thuộc tính đã được kiểm tra.

### 5.3. Soundness và completeness: vì sao có false positive và false negative?

Với một loại lỗi và mô hình đã xác định:

- **Phân tích sound** cho mục tiêu *chứng minh không có lỗi được mô hình hóa* phải bao quát những hành vi cần xét; khi công cụ kết luận “an toàn”, nó không bỏ sót lỗi thuộc phạm vi các giả định đó.
- **Phân tích complete** cho mục tiêu *phát hiện lỗi* không báo những lỗi không tồn tại theo mô hình; trong thực hành, ý nghĩa chính xác của các thuật ngữ này phụ thuộc cách công cụ định nghĩa phát hiện hoặc bảo đảm của mình.

Vì muốn phân tích nhanh và hữu ích trên codebase lớn, nhiều công cụ chấp nhận các đánh đổi:

| Kết quả công cụ | Có thể xảy ra | Cách xử lý phù hợp |
| --- | --- | --- |
| **True positive**: báo vấn đề thật | Có đường đi thực sự vi phạm thuộc tính được kiểm tra. | Sửa nguyên nhân và bổ sung bằng chứng hồi quy. |
| **False positive**: báo nhưng không có lỗi theo hành vi thực | Mô hình thận trọng, không biết một tiền điều kiện hoặc ràng buộc của framework. | Xác minh điều kiện, bổ sung annotation hoặc loại trừ có giải thích. |
| **False negative**: bỏ sót lỗi thực | Phân tích không hỗ trợ kiểu lỗi, giới hạn nguồn lực, dữ liệu động hoặc mô hình chưa đủ. | Dùng các biện pháp bổ sung: test, review, kiểm chứng ranh giới. |
| **Không có cảnh báo** | Chưa phát hiện vấn đề trong phạm vi được kiểm tra. | Không suy diễn thành chứng minh không có lỗi thuộc mọi loại. |

Một công cụ cụ thể có thể đặt tính soundness lên cao cho một số thuộc tính và chấp nhận nhiều cảnh báo; công cụ khác chọn ít cảnh báo hơn nhưng có nguy cơ bỏ sót. Không nên gán chung tính sound hoặc complete cho “mọi static analyzer”.

### 5.4. Symbolic execution, model checking và giới hạn tài nguyên

**Symbolic execution** chạy các đường đi trên đầu vào tượng trưng, tích lũy ràng buộc rồi dùng bộ giải để tìm giá trị khiến đường đi xảy ra. Nó có thể tìm phản ví dụ rất có ích, nhưng số đường đi tăng nhanh theo nhánh, vòng lặp, thao tác thư viện và tương tác môi trường. Hiện tượng này thường gọi là **path explosion**.

**Model checking** kiểm tra thuộc tính trên mô hình trạng thái được xây dựng. Với mô hình hữu hạn được duyệt đầy đủ, nó có thể đưa ra bảo đảm mạnh cho chính mô hình ấy. Nhưng khi phải giới hạn độ dài vết chạy, số trạng thái hoặc đơn giản hóa chi tiết của hệ thống, kết luận chỉ áp dụng trong phạm vi được xét.

Ví dụ, kiểm tra đầy đủ mọi trạng thái của một máy trạng thái nhỏ không đồng nghĩa đã kiểm tra mọi hành vi có thể có của cả ứng dụng Java với database, thread scheduler và mạng.

### 5.5. Phân tích động có cái nhìn gần thực thi nhưng chỉ thấy các lần chạy

Profiling, theo dõi race, kiểm tra memory, ghi trace và các runtime assertion có thể tìm vấn đề trên **những đường đi đã chạy**. Chúng bổ sung cho phân tích tĩnh, đặc biệt với vấn đề phụ thuộc môi trường, nhưng vẫn có giới hạn bao phủ tương tự kiểm thử.

## 6. Ví dụ Java: ba cách nhìn vào lỗi tràn số khi kiểm tra hạn mức

Xét yêu cầu nghiệp vụ đơn giản:

> Một khoản tiền mới được chấp nhận khi tổng đã sử dụng trong ngày và khoản tiền mới cộng lại **không vượt** hạn mức ngày.

Giả định của ví dụ:

- `usedCents` là tổng tiền đã sử dụng trong ngày, kiểu `long` và không âm.
- `incomingCents` là khoản tiền mới, kiểu `long` và **lớn hơn 0**.
- `limitCents` là hạn mức, kiểu `long` và không âm.
- Nếu trạng thái đã sử dụng vượt hạn mức, giao dịch mới bị từ chối.
- Chúng ta đang kiểm tra **một phép quyết định thuần túy**, chưa thực hiện cập nhật dữ liệu đồng thời.

### 6.1. Phiên bản có lỗi ẩn

~~~java
public final class DailyLimit {
    private DailyLimit() {}

    public static boolean canAccept(long usedCents,
                                    long incomingCents,
                                    long limitCents) {
        if (usedCents < 0 || incomingCents <= 0 || limitCents < 0) {
            throw new IllegalArgumentException("Invalid amount");
        }
        return usedCents + incomingCents <= limitCents;
    }
}
~~~

Mã dễ đọc và đúng với nhiều bộ dữ liệu thông thường:

- `usedCents = 90_000`, `incomingCents = 10_000`, `limitCents = 100_000` → `true`.
- `usedCents = 90_000`, `incomingCents = 10_001`, `limitCents = 100_000` → `false`.

Nhưng với `usedCents = Long.MAX_VALUE - 5`, `incomingCents = 10`, `limitCents = Long.MAX_VALUE`, phép cộng `long` tràn số thành giá trị âm. Phương thức sẽ trả về `true` dù tổng toán học vượt hạn mức.

Đây là lỗi mà:

- **Suy luận** có thể phát hiện khi xét đúng miền giá trị của kiểu `long`.
- **Kiểm thử** có thể phát hiện nếu chọn ca tràn số và kiểm tra kết quả mong đợi.
- **Phân tích tự động** có thể cảnh báo nếu công cụ được cấu hình và có khả năng theo dõi phép cộng với miền giá trị phù hợp. Không thể mặc định trình biên dịch Java sẽ cảnh báo lỗi này.

### 6.2. Thiết kế lại phép so sánh để không cộng tràn

~~~java
public final class DailyLimit {
    private DailyLimit() {}

    public static boolean canAccept(long usedCents,
                                    long incomingCents,
                                    long limitCents) {
        if (usedCents < 0 || incomingCents <= 0 || limitCents < 0) {
            throw new IllegalArgumentException("Invalid amount");
        }
        return usedCents <= limitCents
                && incomingCents <= limitCents - usedCents;
    }
}
~~~

Tại sao cách này an toàn hơn với **tiền điều kiện đã nêu**?

1. Mọi giá trị đầu vào đều không âm, và khoản thêm phải dương.
2. Nếu `usedCents > limitCents`, biểu thức đầu tiên trả `false`; do `&&` ngắn mạch, Java không cần đánh giá phần trừ.
3. Nếu `usedCents <= limitCents`, hiệu `limitCents - usedCents` nằm trong đoạn từ 0 đến `Long.MAX_VALUE`, nên không tràn số.
4. So sánh `incomingCents <= limitCents - usedCents` tương đương với yêu cầu tổng không vượt hạn mức trong số học nguyên, nhưng không tạo tổng có nguy cơ tràn.

Lập luận này **không áp dụng nguyên xi** nếu bỏ điều kiện không âm hoặc thay đổi loại dữ liệu. Chính tiền điều kiện làm cho phép biến đổi đại số an toàn trong Java.

Một cách khác là dùng `Math.addExact(usedCents, incomingCents)`, hàm ném `ArithmeticException` khi phép cộng tràn số, sau đó quyết định xử lý ngoại lệ theo hợp đồng. Cách trừ như trên phù hợp khi ta chỉ muốn trả về `false` cho khoản vượt hạn mức và không cần tính tổng.

### 6.3. Unit test cho yêu cầu và ranh giới nguy hiểm

Với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DailyLimitTest {
    @Test
    void acceptsExactlyAtLimit() {
        assertTrue(DailyLimit.canAccept(90_000, 10_000, 100_000));
    }

    @Test
    void rejectsOneUnitAboveLimit() {
        assertFalse(DailyLimit.canAccept(90_000, 10_001, 100_000));
    }

    @Test
    void rejectsOverflowingAddition() {
        assertFalse(DailyLimit.canAccept(
                Long.MAX_VALUE - 5, 10, Long.MAX_VALUE));
    }

    @Test
    void rejectsAlreadyExceededLimit() {
        assertFalse(DailyLimit.canAccept(110_000, 1, 100_000));
    }

    @Test
    void rejectsInvalidIncomingAmount() {
        assertThrows(IllegalArgumentException.class,
                () -> DailyLimit.canAccept(10_000, 0, 100_000));
    }
}
~~~

Bài test thứ ba bắt được lỗi của phiên bản đầu tiên. Các test khác kiểm tra đúng ngưỡng, vượt ngưỡng, trạng thái đã sai và hợp đồng đầu vào. Chúng cung cấp **bằng chứng thực thi** cho các ca được chọn; lập luận về phép trừ ở phần trước giúp giải thích tại sao giải pháp còn đúng đối với các giá trị hợp lệ khác.

### 6.4. Vì sao “đúng ở mức hàm” chưa đủ?

Giả sử có hai giao dịch mới cùng lúc, mỗi giao dịch là 20.000, trong khi tổng đã dùng là 70.000 và hạn mức 100.000. Nếu hai luồng cùng đọc giá trị 70.000 rồi độc lập gọi `canAccept(70_000, 20_000, 100_000)`, cả hai đều nhận `true`.

Nếu cả hai khoản tiền đều được ghi nhận, tổng thực là 110.000 — vượt hạn mức.

~~~text
Luồng A                         Luồng B
-------                         -------
Đọc used = 70.000               Đọc used = 70.000
Kiểm tra +20.000 → hợp lệ       Kiểm tra +20.000 → hợp lệ
Ghi nhận +20.000                Ghi nhận +20.000
             \                  /
             Tổng ghi nhận = 110.000
~~~

Lỗi nằm ở **tính nguyên tử và sự phối hợp cập nhật trạng thái**, không nằm trong phép so sánh đơn lẻ. Một giải pháp thực tế có thể cần giao dịch database với cơ chế khóa, điều kiện cập nhật nguyên tử, hoặc mức cô lập thích hợp — tùy hệ quản trị và thiết kế dữ liệu. Cần kiểm thử tích hợp, xem xét tình huống đồng thời và kiểm chứng cơ chế lưu trữ đã chọn.

Ngay cả khi unit test, static analyzer và suy luận về hàm `DailyLimit` đều đạt, **toàn bộ nghiệp vụ vẫn có thể sai** nếu điểm cập nhật không bảo đảm cùng một bất biến.

## 7. Chọn bằng chứng theo câu hỏi cần trả lời

| Câu hỏi về tính đúng đắn | Bằng chứng nên phối hợp | Kết luận vẫn cần giới hạn |
| --- | --- | --- |
| Phép kiểm tra hạn mức có tránh tràn số không? | Tiền điều kiện và lập luận về `long`; test tại giá trị biên; kiểm tra static analyzer nếu có. | Chỉ trong miền giá trị và hợp đồng đã mô tả. |
| Hai yêu cầu đồng thời có làm vượt hạn mức không? | Xem xét thiết kế giao dịch và tính nguyên tử; test tích hợp cạnh tranh truy cập; giám sát bất biến dữ liệu. | Test nhiều luồng không duyệt hết mọi lịch thực thi; bảo đảm phụ thuộc DB và cơ chế khóa. |
| API có giữ tương thích cho client cũ không? | Contract test, schema validation, kiểm thử tích hợp với phiên bản client cần hỗ trợ. | Chỉ với các phiên bản, trường hợp và cách gọi được xác định. |
| Quy tắc chiết khấu đúng với nghiệp vụ không? | Tiêu chí chấp nhận từ người phụ trách; bảng quyết định; review test oracle; các ca biên. | Một đặc tả sai hoặc thiếu vẫn khiến test “xanh” cho hành vi không mong muốn. |
| Mã có an toàn với đầu vào bất thường không? | Kiểm tra hợp đồng dữ liệu, fuzzing, phân tích tĩnh, kiểm thử ngoại lệ và phân quyền. | Công cụ chỉ kiểm tra một tập lớp lỗi; không thể suy ra bảo đảm an toàn tổng quát. |
| Có thể chứng minh một thuật toán luôn kết thúc không? | Lập luận về biến thể vòng lặp, tiền điều kiện; chứng minh hoặc phân tích trên mô hình thích hợp. | Phải bao gồm các tác nhân gây chờ vô hạn như I/O và đồng bộ nếu thuộc phạm vi. |

### 7.1. Không phải càng nhiều công cụ là càng nhiều bảo đảm

Năm công cụ cùng báo một mẫu lỗi tương tự không nhất thiết cung cấp năm nguồn bằng chứng độc lập. Cần phân biệt **mức độ bao phủ thuộc tính**, **sự độc lập của giả định** và **chất lượng của cách kiểm chứng**.

Ví dụ, một bài unit test do chính người viết logic xây dựng có thể lặp lại cùng giả định sai. Review tiêu chí chấp nhận bởi người hiểu nghiệp vụ là một nguồn kiểm tra khác có thể phát hiện sai lệch mà thêm test cùng oracle chưa giải quyết.

### 7.2. Xác định rõ phạm vi của mỗi kết quả

Một báo cáo có ích nên chỉ ra:

- **Phiên bản mã và cấu hình:** kết quả gắn với commit, dependency và môi trường nào?
- **Thuộc tính được xem xét:** không tràn số, không null, không vượt hạn mức, không mất cập nhật hay điều gì khác?
- **Dữ liệu và trạng thái:** đã kiểm tra những đầu vào, tải, thời điểm hoặc biến thể nào?
- **Giả định:** múi giờ, tính hợp lệ của dữ liệu, hành vi mock, tính nguyên tử của DB, cấu hình công cụ ra sao?
- **Điều chưa kiểm tra:** ranh giới hệ thống, loại rủi ro hoặc trường hợp ngoài phạm vi.

Cách trình bày này làm kết luận dễ review và tái sử dụng khi mã được thay đổi.

## 8. Những ngộ nhận thường gặp

### “Nếu đủ unit test thì không cần suy luận”

Không đúng. Test cần oracle, cần chọn đầu vào và không bao phủ toàn bộ trạng thái trong các hệ thống không tầm thường. Suy luận giúp tìm ra bất biến, trường hợp biên và chỗ một phép biến đổi có thể sai.

### “Nếu đã chứng minh thuật toán thì không cần test”

Chứng minh có thể rất mạnh, nhưng sản phẩm chạy còn phụ thuộc vào triển khai, cấu hình, thư viện, kết nối và giả định môi trường. Kiểm thử giúp đối chiếu mô hình với hiện thực và phát hiện lỗi tích hợp.

### “Code coverage 100% là bảo đảm không còn bug”

Không đúng. Dòng lệnh đã chạy chưa chắc được kiểm tra bằng assertion đúng; coverage không tự chứng minh tính đúng đắn của mọi đầu vào, trạng thái hoặc lịch thực thi.

### “Static analyzer im lặng nghĩa là code an toàn”

Không đúng. Cần đọc loại thuộc tính mà công cụ hỗ trợ, phạm vi phân tích, cấu hình loại trừ và các hạn chế đã biết. Không có cảnh báo có thể chỉ là không tìm thấy vấn đề thuộc lớp công cụ kiểm tra.

### “Đã có fuzzing thì mọi đầu vào lạ đều được kiểm tra”

Không đúng. Fuzzing có thể chạy nhiều đầu vào bất thường rất hiệu quả, nhưng vẫn phụ thuộc cách sinh dữ liệu, khả năng chạm tới đường đi quan trọng và oracle phát hiện lỗi.

### “Một test lỗi thất thường chỉ cần chạy lại đến khi đỗ”

Không đúng. Test không ổn định có thể là dấu hiệu race condition, phụ thuộc thời gian hoặc môi trường không được kiểm soát. Chạy lại giúp thu thập thêm dấu vết, nhưng không thay thế điều tra nguyên nhân.

## 9. Quy trình thực tế để tăng độ tin cậy khi sửa mã Java

Khi nhận một yêu cầu hoặc bug report, có thể đi theo trình tự:

1. **Làm rõ đặc tả:** viết yêu cầu thành tiêu chí chấp nhận đo được, nêu các tiền điều kiện và những tình huống ngoài phạm vi.
2. **Xác định bất biến:** điều gì phải luôn đúng trước và sau thao tác, ngay cả khi có lỗi hoặc nhiều yêu cầu đồng thời?
3. **Suy luận về đường đi rủi ro:** chú ý miền giá trị số học, null, trạng thái, thời gian, ngoại lệ, tương tranh và phụ thuộc bên ngoài.
4. **Thiết kế test có mục đích:** chọn ca thông thường, biên, sai đầu vào và ca từng gây sự cố; đừng chỉ chạy hàm để tăng coverage.
5. **Chạy công cụ phù hợp:** biên dịch, lint, phân tích tĩnh, test tự động và những kiểm tra chuyên biệt cho kiểu lỗi đang quan tâm.
6. **Kiểm tra ranh giới thật:** dùng integration/contract/end-to-end test khi cần xác minh database, API, phân quyền, thời gian hoặc đồng thời.
7. **Diễn giải kết quả đúng mức:** lỗi nào đã được tìm thấy, thuộc tính nào đã được bảo vệ, phần nào chưa có bằng chứng?
8. **Giữ lại bằng chứng hồi quy:** lưu test, giả định và lý do của sửa đổi ở nơi người bảo trì sau có thể tiếp cận.

Không nhất thiết áp dụng mọi công cụ cho mọi thay đổi. Ví dụ, sửa tên biến không cần một mô hình hóa hình thức phức tạp; thay đổi phép tính tiền và xử lý đồng thời có thể cần kiểm tra sâu hơn. **Mức đầu tư nên tương xứng với rủi ro và hậu quả khi sai.**

## 10. Bài tập tự đánh giá

### Tình huống A: Hàm tìm giá trị lớn nhất

Một nhóm có hàm tính giá trị lớn nhất trong mảng số nguyên. Họ viết test cho mảng gồm ba phần tử dương và test đã đỗ.

**Hỏi:** đã có bằng chứng cho những tình huống nào? Còn thiếu điều gì?

**Gợi ý:** cần làm rõ hợp đồng với mảng rỗng, mảng chứa giá trị âm, giá trị trùng, `Integer.MIN_VALUE`, `null` và mảng rất lớn. Những trường hợp cụ thể phụ thuộc hợp đồng API; không thể tự chọn hành vi cho mảng rỗng nếu yêu cầu chưa quy định. Có thể suy luận về bất biến vòng lặp: sau khi xử lý phần tử thứ `i`, biến `max` bằng giá trị lớn nhất của đoạn đã duyệt.

### Tình huống B: Công cụ báo an toàn

Một static analyzer được bật cho dự án và trả về không cảnh báo mới. Trong production, ứng dụng vẫn lỗi khi hai request cập nhật cùng bản ghi.

**Hỏi:** kết quả công cụ có mâu thuẫn với sự cố không?

**Gợi ý:** không nhất thiết. Công cụ có thể không phân tích hành vi giao dịch đồng thời hoặc thiếu mô hình database. Cần kiểm tra phạm vi mà công cụ hỗ trợ, sau đó phân tích tính nguyên tử của thao tác và xây dựng kiểm thử tích hợp thích hợp.

### Tình huống C: Test xanh nhưng kết quả sai

Người viết mã nhận yêu cầu “phí giao hàng bằng 0 nếu đơn từ 500.000 trở lên”. Bộ test chỉ có đầu vào 200.000 và 600.000; mọi test đỗ. Người dùng khiếu nại đơn đúng 500.000 vẫn bị tính phí.

**Hỏi:** nên bổ sung gì và tại sao?

**Gợi ý:** thêm test đúng ngưỡng và sát hai bên ngưỡng. Rà soát điều kiện `>` và `>=`, đồng thời xác nhận cách tính tổng trước/sau giảm giá. Test mới phải dựa trên tiêu chí nghiệp vụ rõ ràng, không sao chép hành vi của phiên bản lỗi.

## 11. Checklist khi review một kết luận “mã đã đúng”

- [ ] Tôi biết “đúng” theo yêu cầu nào, ở phạm vi hàm, module hay toàn hệ thống.
- [ ] Tôi đã nêu tiền điều kiện, hậu điều kiện, dữ liệu không hợp lệ và những trường hợp biên quan trọng.
- [ ] Những phép toán số học được xét theo miền giá trị thực của kiểu Java.
- [ ] Tôi biết test oracle đến từ yêu cầu nào và đã có người phù hợp xác nhận khi cần.
- [ ] Test có assertion kiểm tra hành vi; coverage không được dùng làm bằng chứng duy nhất.
- [ ] Các báo cáo phân tích tự động được hiểu theo đúng loại lỗi, cấu hình và giới hạn của công cụ.
- [ ] Những phụ thuộc ngoài, giao dịch, đồng thời, thời gian và lỗi môi trường đã được cân nhắc.
- [ ] Bằng chứng gắn được với phiên bản mã và môi trường kiểm tra.
- [ ] Phần chưa chứng minh hoặc chưa kiểm tra được ghi nhận rõ để người tiếp theo không suy diễn quá mức.
- [ ] Mức kiểm chứng tương xứng với rủi ro thực tế của thay đổi.

## 12. Kết luận

**Suy luận** giúp xây dựng lý do vì sao một thuộc tính phải đúng trong những điều kiện xác định. **Kiểm thử** cung cấp bằng chứng từ các lần thực thi và có thể tạo phản ví dụ rất cụ thể. **Phân tích tự động** mở rộng khả năng rà soát, nhưng phạm vi bảo đảm phụ thuộc vào mô hình, công cụ, cấu hình và tài nguyên.

Ba cách tiếp cận bổ sung cho nhau. Đối với mục tiêu của **CODE_QUALITY_FUNDAMENTALS** — viết mã đáng tin cậy, dễ hiểu và dễ thay đổi — điều quan trọng là mô tả đúng **thuộc tính cần bảo vệ**, xây dựng bằng chứng phù hợp và nói rõ **giả định cùng giới hạn của kết luận**. Nhờ vậy, người bảo trì có thể sửa mã với sự tự tin có cơ sở, thay vì dựa vào cảm giác hoặc một chỉ số kiểm tra đơn lẻ.

