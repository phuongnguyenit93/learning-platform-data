# Tính duy nhất và nhiều cây khung tối ưu

**Cây khung nhỏ nhất** (*minimum spanning tree*, viết tắt **MST**) của một **đồ thị vô hướng liên thông, có trọng số** là một cây sử dụng tất cả đỉnh, có đúng `V−1` cạnh và có **tổng trọng số cạnh nhỏ nhất** trong mọi cây khung. Một đồ thị có thể có **một MST duy nhất** hoặc **nhiều MST khác nhau nhưng có cùng tổng trọng số tối ưu**. Câu hỏi “tính duy nhất” không phải chỉ hỏi tổng trọng số: thuật toán cần chứng minh **không tồn tại một tập cạnh khác** cũng tạo thành cây khung với đúng chi phí tối ưu.

Điều thường gây nhầm lẫn là **cạnh có trọng số bằng nhau không tự động khiến MST không duy nhất**. Trọng số của mọi cạnh **đôi một khác nhau** bảo đảm MST duy nhất, nhưng điều kiện ấy chỉ là **đủ, không cần thiết**. Ngược lại, hai cây khung khác nhau có thể có cùng tổng trọng số ngay cả khi thuật toán Kruskal hoặc Prim luôn trả ra một tập cạnh cố định do quy tắc phá hòa.

Bài thuộc nhóm **Cây khung**. Ta sẽ xây dựng khái niệm chính xác; dùng **tính chất cắt** và **tính chất chu trình** để lý giải việc chọn cạnh; chứng minh tiêu chí hoán đổi cạnh; kiểm tra tính duy nhất bằng **Kruskal xử lý cả nhóm cạnh đồng trọng số**; viết chương trình **Java 17+** chạy độc lập, hỗ trợ **cạnh song song**, **self-loop**, **trọng số âm** và đồ thị không liên thông; phân biệt việc tìm một MST, kiểm tra nhiều MST và **đếm số MST**; cuối cùng là bộ kiểm thử vét cạn độc lập.

**Mục tiêu:** phát biểu được khi nào MST là duy nhất; nhận ra trường hợp bằng trọng số nhưng vẫn duy nhất; giải thích vì sao một cạnh không thuộc MST có thể hoán đổi với một cạnh trên đường cây mà giữ nguyên tổng; hiểu đồ thị co theo các cạnh nhẹ hơn trong Kruskal; cài thuật toán phát hiện nhiều MST trong `O(E log E)` cộng thao tác DSU; xử lý đồ thị không có cây khung.

## 1. Mô hình bài toán và ý nghĩa “khác nhau”

Xét đồ thị vô hướng `G=(V,E)` có `n=|V|≥1` đỉnh đánh số `0..n−1` và `m=|E|` cạnh. Mỗi cạnh e nối hai đầu mút u,v, có trọng số `w(e)`; trọng số có thể âm, bằng 0 hoặc dương. Trong mô hình tổng quát ta cho phép **đa cạnh** giữa cùng một cặp đỉnh và **self-loop** nối một đỉnh với chính nó.

Một **cây khung** T thỏa:

1. Chứa **tất cả n đỉnh**.
2. Có đúng **n−1 cạnh**.
3. **Liên thông**.
4. **Không có chu trình**.

Bất kỳ ba điều kiện cấu trúc phù hợp nào cũng có thể giúp suy ra điều còn lại, nhưng khi kiểm thử nên kiểm tra tính liên thông và không chu trình. Trọng số của T là:

**`W(T)=Σ_{e∈T}w(e)`.**

Một **MST** thỏa `W(T)=min_{T' là cây khung} W(T')`.

### Nhiều MST là nhiều **tập cạnh** tối ưu

Nếu có hai tập cạnh **khác nhau** `T₁≠T₂`, đều là cây khung và cùng đạt trọng số nhỏ nhất, thì đồ thị có **nhiều MST**. Không yêu cầu tổng trọng số khác nhau: chính sự **bằng nhau ở mức tối ưu** làm xuất hiện nhiều lựa chọn.

Với **cạnh song song**, ta gán mỗi cạnh một **ID riêng** theo vị trí nhập. Hai cạnh cùng đầu mút và cùng trọng số vẫn được coi là hai đối tượng cạnh khác nhau; chọn cạnh ID 0 hoặc ID 1 có thể tạo hai cây khung khác nhau, dù bản vẽ với hai đầu mút giống hệt. Nếu một đề bài coi cạnh song song trùng nhau là không phân biệt, phải sửa định nghĩa số phương án phù hợp.

**Self-loop** không thể thuộc cây khung vì nó tạo chu trình độ dài một mà không giúp nối các đỉnh. Do đó một self-loop âm rất rẻ cũng **không** được chọn vào MST. Tương tự, một cạnh âm nối hai thành phần khác nhau có thể hoàn toàn hợp lệ trong MST.

### Điều kiện đồ thị liên thông

Nếu n>1 và đồ thị không liên thông, **không tồn tại cây khung bao phủ mọi đỉnh**, nên cũng **không có MST** cho toàn đồ thị. Khi ấy câu “MST duy nhất hay nhiều” **không có đối tượng để xét**. Ta có thể dùng **rừng khung nhỏ nhất** (*minimum spanning forest*, MSF) cho các thành phần liên thông, nhưng đó là bài toán khác và phải được nêu rõ.

Chương trình Java bên dưới trả trạng thái **DISCONNECTED** thay vì gọi một rừng tìm được là MST. Với **n=1**, cây khung gồm một đỉnh và **không cạnh**, tổng trọng số 0; đó là cây khung duy nhất, kể cả nếu input có self-loop.

## 2. Ba ví dụ trực giác quan trọng

### 2.1. Tất cả cạnh của một tam giác đều bằng 2

Cho ba đỉnh 0,1,2 và các cạnh có ID:

- `e₀=(0,1,2)`.
- `e₁=(1,2,2)`.
- `e₂=(0,2,2)`.

Mỗi cây khung phải chọn hai trong ba cạnh, nên đều có trọng số **4**:

| MST | Cạnh chọn | Tổng |
|---|---|---:|
| T₁ | `{e₀,e₁}` | 4 |
| T₂ | `{e₀,e₂}` | 4 |
| T₃ | `{e₁,e₂}` | 4 |

Có **3 MST khác nhau**. Kruskal có thể chọn `{e₀,e₁}` do thứ tự ID, nhưng điều đó không có nghĩa MST duy nhất.

### 2.2. Nhiều cạnh bằng nhau nhưng MST vẫn duy nhất

Cho bốn đỉnh với các cạnh:

- `e₀=(0,1,1)`, `e₁=(0,2,1)`, `e₂=(0,3,1)`.
- `e₃=(1,2,3)`, `e₄=(2,3,4)`.

Ba cạnh trọng số 1 tạo một cây hình sao nối mọi đỉnh. Tổng tối ưu là **3**, và **chỉ có cây `{e₀,e₁,e₂}` đạt tổng 3**: thay bất kỳ cạnh 1 nào bằng cạnh 3 hoặc 4 sẽ tăng tổng, trong khi thêm cạnh mới mà không bỏ cạnh cũ sẽ tạo chu trình.

Ví dụ này chứng minh: **có cạnh bằng trọng số** không đủ kết luận có nhiều MST. Chúng phải thực sự là các lựa chọn thay thế ở những phần của đồ thị.

### 2.3. Hai cạnh song song bằng nhau

Hai đỉnh 0,1, hai cạnh riêng biệt:

- `e₀=(0,1,5)`.
- `e₁=(0,1,5)`.

Cây khung chỉ cần một cạnh. Chọn e₀ hoặc e₁ đều được tổng **5** ⇒ **2 MST** theo ID cạnh. Dưới dạng đồ thị đa cạnh, hai cạnh song song tạo một chu trình có độ dài hai trong lập luận hoán đổi; một DSU tạm phải phát hiện được sự cạnh tranh này.

## 3. Tính chất cắt: khi nào một cạnh bị buộc phải chọn?

Một **cut** phân hoạch đỉnh thành hai tập không rỗng `S` và `V\S`. Cạnh **băng qua cut** là cạnh có một đầu trong S, đầu kia ở V\S.

**Tính chất cắt:** nếu một cạnh e có trọng số **nhỏ nhất và nhỏ hơn nghiêm ngặt mọi cạnh khác băng qua một cut**, e phải thuộc **mọi MST**.

Chứng minh bằng hoán đổi:

1. Giả sử có MST T không chứa e.
2. Thêm e vào T tạo **một chu trình**.
3. Đường trong T nối hai đầu e phải vượt qua cut ít nhất một lần, nên trong chu trình có cạnh f thuộc T cũng băng qua cut.
4. Vì e là cạnh **rẻ nhất duy nhất** qua cut, `w(e)<w(f)`.
5. Thay f bằng e tạo cây khung nhẹ hơn T, mâu thuẫn T tối ưu.

Vậy e bắt buộc có trong mọi MST.

### Nếu có nhiều cạnh cùng nhẹ nhất qua cut?

Khi cạnh e chỉ **đồng hạng nhỏ nhất**, tính chất cắt cho biết có một MST chứa e trong những điều kiện chuẩn, nhưng **không thể kết luận mọi MST đều phải chứa e**. Cũng không có nghĩa tất cả các cạnh đồng hạng đều có thể đồng thời thuộc cùng MST: chúng có thể tạo chu trình.

Ví dụ tam giác ba cạnh trọng số 2: đối với cut `{0}|{1,2}`, hai cạnh 0–1 và 0–2 đồng hạng nhẹ nhất. Chọn một trong hai vẫn có cơ hội tạo MST; không cạnh nào bắt buộc phải có trong **tất cả** ba MST.

Trong ví dụ hình sao, cut `{1}|{0,2,3}` có cạnh 0–1 trọng số 1, còn 1–2 trọng số 3; do đó 0–1 là cạnh nhẹ nhất duy nhất và **bắt buộc**. Tương tự với các lá khác; ba cạnh trọng số 1 đồng thời bị buộc, tạo MST duy nhất.

## 4. Tính chất chu trình: cạnh nào không được chọn?

Với bất kỳ chu trình C, nếu cạnh e là **cạnh nặng nhất duy nhất** trong C, e **không thuộc bất kỳ MST nào**.

Lý do: nếu một cây khung T chứa e, bỏ e làm tách cây thành hai phần; vì C có một đường vòng khác nối hai đầu e mà không đi qua e, tồn tại một cạnh f trên đường vòng băng qua hai phần của cây. Mọi cạnh khác trên C nhẹ hơn e, nên thay e bằng f tạo cây khung nhẹ hơn, mâu thuẫn tính tối ưu.

Nếu trên chu trình có **nhiều cạnh cùng nặng nhất**, không thể loại chúng chỉ từ tính chất chu trình nghiêm ngặt. Một số cạnh đồng hạng có thể xuất hiện ở các MST khác nhau.

**So sánh nhanh:**

- Cạnh **nhẹ nhất duy nhất của một cut** ⇒ thuộc **mọi MST**.
- Cạnh **nặng nhất duy nhất trên một chu trình** ⇒ thuộc **không MST nào**.
- Cạnh đồng hạng ở cut/chu trình ⇒ cần xét thêm; không tự động có nhiều MST.

### Trọng số âm có thay đổi các định lý này không?

Không. Chứng minh chỉ dùng thứ tự so sánh trọng số và việc thay cạnh trong cây, nên áp dụng cho số âm, số 0 và số dương. Không được chọn một self-loop âm vì nó vẫn là chu trình, không giúp kết nối đỉnh.

## 5. Trọng số khác nhau: đủ nhưng không cần

**Định lý:** nếu tất cả cạnh của đồ thị vô hướng liên thông có trọng số **đôi một phân biệt**, MST là **duy nhất**.

Một cách chứng minh bằng cut: chạy Kruskal. Ở mỗi bước, cạnh được chọn có trọng số nhỏ hơn mọi cạnh còn có thể nối cùng hai phía của cut tương ứng; do trọng số phân biệt, cạnh ấy là lựa chọn nhẹ nhất nghiêm ngặt của cut và bị buộc trong mọi MST. Lặp lại cho n−1 cạnh, ta được một cây duy nhất.

**Không được đảo chiều mệnh đề:**

- “Mọi trọng số phân biệt ⇒ MST duy nhất”: **đúng**.
- “MST duy nhất ⇒ mọi trọng số phân biệt”: **sai** (ví dụ hình sao ba cạnh trọng số 1).

Có thể có rất nhiều cạnh cùng trọng số nhưng **không cạnh nào tạo lựa chọn hoán đổi ngang giá**, nên MST vẫn duy nhất.

### Một trường hợp cạnh đồng trọng số nhưng không liên quan

Nếu hai cạnh cùng trọng số nằm ở **hai phần khác nhau và đều bắt buộc** để nối đỉnh, chúng không cạnh tranh với nhau. Từ góc độ Kruskal, nhóm cạnh cùng trọng số sau khi co các thành phần nhẹ hơn vẫn có thể là một **rừng không chu trình**. Đó chính là tiêu chí được triển khai trong mục tiếp theo.

## 6. Tiêu chí hoán đổi cạnh: kiểm tra trực tiếp từ một MST

Giả sử T là **một MST bất kỳ** của đồ thị liên thông. Với mỗi cạnh **e=(u,v)** không thuộc T và **u≠v**, trong T có **một đường đơn duy nhất** `P_T(u,v)` nối hai đầu e.

Gọi:

**`M_T(u,v)=max_{f∈P_T(u,v)} w(f)`.**

Khi thêm e vào T, ta tạo một chu trình gồm e cộng với đường P. Bỏ một cạnh f trên đường ấy thì trở lại một cây khung, có trọng số:

**`W(T−f+e)=W(T)−w(f)+w(e)`.**

Vì T đã là MST nên không thể có một phép thay làm giảm tổng. Chọn f nặng nhất trên P, ta suy ra:

**`w(e)≥M_T(u,v)`** đối với mọi cạnh không thuộc MST T.

Đây cũng là một cách kiểm tra tính tối ưu của T: nếu tồn tại e không nằm trong T với `w(e)<M_T(u,v)` thì T **không thể là MST**, vì ta có cách thay cạnh làm nhẹ cây hơn.

### Tiêu chí chính xác cho tính duy nhất

Với một MST T đã xác nhận đúng:

- Nếu tồn tại cạnh e không thuộc T, không phải self-loop, thỏa **`w(e)=M_T(u,v)`**, thì **MST không duy nhất**. Ta có thể thay e cho một cạnh f nặng nhất trên P và tạo cây khác nhưng cùng tổng.
- Nếu **mọi cạnh e không thuộc T** đều thỏa **`w(e)>M_T(u,v)`**, thì **T là MST duy nhất**.
- Trường hợp `w(e)<M_T(u,v)` chứng minh T **không tối ưu**, không phải chỉ “có nhiều MST”.

**Lưu ý về self-loop:** e=(u,u) không tạo chu trình trao đổi hợp lệ với một cạnh cây khác; đường P_T(u,u) rỗng. Phải **bỏ qua self-loop** trong phép kiểm tra M_T.

### Chứng minh chiều “không có dấu bằng ⇒ duy nhất”

Giả sử với mọi non-tree edge e, `w(e)>M_T(e)`. Xét một cạnh f bất kỳ của T. Bỏ f chia cây thành hai phần S và V\S. Mọi cạnh ngoài T băng qua cut này đều có đường P_T(e) chứa f. Do đó với chúng:

`w(e)>M_T(e)≥w(f)`.

Vậy f là **cạnh nhẹ nhất duy nhất qua cut** (vì cây T chỉ có chính f băng qua fundamental cut ấy). Theo tính chất cắt, f thuộc **mọi MST**. Mọi f của T đều bị buộc, nên mọi MST phải chứa đúng tập cạnh T; T là duy nhất.

**Chiều có dấu bằng** dùng phép thay cạnh trực tiếp và không cần định lý phức tạp: với `w(e)=w(f)`, cây mới `T'=T−f+e` có tổng bằng W(T) và khác T theo ID cạnh.

### Dựng một nhân chứng MST thứ hai

Có thể thực hiện như sau:

1. Chạy Kruskal lấy một MST T và đánh dấu ID các cạnh đã chọn.
2. Với mỗi non-tree edge e=(u,v), bỏ self-loop, tìm đường duy nhất từ u tới v trên T.
3. Tìm một cạnh f có **trọng số lớn nhất** trên đường ấy.
4. Nếu `w(e)=w(f)`, trả hai cây: T và `T−f+e`.

Cách cài đơn giản tìm đường bằng BFS/DFS từ đầu mút e trên cây mất **O(V)** cho mỗi e, tổng **O(EV)** sau khi đã có MST. Với nhiều truy vấn, có thể tiền xử lý **LCA/binary lifting** trên cây để lấy trọng số lớn nhất của đường trong O(log V) mỗi e, đưa bước kiểm tra về **O((V+E)log V)** sau khi xây cây.

**Tuy nhiên:** nếu chỉ cần một boolean “duy nhất hay không”, có cách kiểm tra trực tiếp trong quá trình Kruskal nhanh và gọn hơn: xét **đồng thời cả nhóm cạnh cùng trọng số**.

## 7. Kruskal và vấn đề xử lý thứ tự phá hòa

**Kruskal** sắp các cạnh theo trọng số tăng dần. Ban đầu mỗi đỉnh là một thành phần riêng trong cấu trúc **DSU/Union-Find**. Với mỗi cạnh e=(u,v), nếu hai đầu thuộc hai thành phần khác nhau thì chọn e vào rừng và hợp nhất chúng; nếu đã thuộc cùng thành phần thì bỏ e vì nó tạo chu trình.

Nhờ tính chất cắt, Kruskal trả một MST khi đồ thị liên thông, với thời gian chủ yếu do sắp cạnh `O(E log E)` và các thao tác DSU gần tuyến tính.

### Tại sao kết quả Kruskal chỉ là “một MST”?

Nếu các cạnh có cùng trọng số, việc sắp có thể phá hòa theo:

- ID cạnh;
- thứ tự nhập;
- thứ tự đầu mút;
- hành vi sắp xếp khi comparator trả 0.

Một lựa chọn cố định giúp chương trình in một cây **tái lập được**, nhưng không cung cấp bằng chứng rằng **không có lựa chọn khác**. Trong tam giác đều, comparator theo ID luôn chọn e₀ rồi e₁, song e₂ hoàn toàn có thể thay e₀ hoặc e₁ mà không đổi tổng.

### Sai lầm nguy hiểm: union=false nghĩa là “nhiều MST”?

Không. Cạnh không được Kruskal chọn có thể bị loại vì **nặng hơn rõ rệt**. Ví dụ tam giác có trọng số 1,2,3: Kruskal chọn 1 và 2; cạnh 3 có hai đầu đã nối, nên union=false, nhưng thay vào sẽ tăng tổng. MST vẫn duy nhất.

Ngay cả khi cạnh cùng trọng số được xét sau khi DSU đã union vài cạnh **trong cùng nhóm**, việc nhìn union=false đơn lẻ cũng chưa đủ nếu không phân biệt nó với cạnh đã bị nối từ **những nhóm trọng số nhỏ hơn**. Muốn kiểm tra tính duy nhất, phải chụp trạng thái DSU **trước** khi xử lý toàn bộ nhóm trọng số w.

## 8. Tiêu chí theo nhóm cạnh đồng trọng số

Đây là cách kiểm tra nhiều MST ngay trong Kruskal, không cần truy vấn max trên đường cây.

Giả sử đã xét tất cả cạnh có trọng số **nhỏ hơn w**. DSU chính lúc này biểu diễn các thành phần liên thông khi chỉ cho phép dùng những cạnh trọng số `<w`. Ta tạm thời **co mỗi thành phần DSU thành một siêu đỉnh**.

Xét tất cả cạnh có trọng số **đúng bằng w**:

- Nếu hai đầu đã ở **cùng thành phần DSU chính**, cạnh đó bị loại khỏi đồ thị co của nhóm w: hai đầu đã nối bằng các cạnh rẻ hơn. Cạnh này không tạo lựa chọn ngang giá trong MST.
- Nếu hai đầu thuộc **hai thành phần DSU khác nhau**, tạo một cạnh giữa hai siêu đỉnh tương ứng.
- Giữ **mỗi cạnh gốc có ID riêng**, kể cả hai cạnh song song; không được khử trùng các cạnh này.

Đồ thị đa cạnh thu được gọi là **`H_w` — đồ thị các cạnh cùng trọng số sau khi co những cạnh nhẹ hơn**.

### Định lý quan trọng

Với đồ thị gốc liên thông:

**MST là duy nhất ⇔ với mọi nhóm trọng số w, đồ thị đa cạnh `H_w` không chứa chu trình.**

Nói cách khác, **nếu tồn tại một nhóm w mà `H_w` có chu trình, thì có nhiều MST**.

Ở đây chu trình trong **multigraph** bao gồm cả **hai cạnh song song** nối cùng cặp siêu đỉnh. Self-loop hoặc cạnh có hai đầu đã nằm trong cùng thành phần nhẹ hơn không được xem là cạnh cạnh tranh trong `H_w`.

### Vì sao chu trình trong `H_w` gây nhiều MST?

Trong một nhóm có trọng số w, Kruskal cần lấy đủ các cạnh để kết nối các thành phần của mỗi thành phần liên thông trong `H_w` mà không tạo chu trình. Mọi cạnh của nhóm đều có **cùng trọng số**, nên:

- Nếu `H_w` là rừng, mọi cạnh của nó đều cần được chọn để đạt mức liên thông của nhóm trước khi sang trọng số nặng hơn; không có lựa chọn thay thế.
- Nếu `H_w` có chu trình, ta có thể chọn các **rừng khung khác nhau** trong cùng một thành phần liên thông của nhóm, đều dùng cùng số cạnh, cùng tổng trọng số w·số_cạnh. Những lựa chọn đó có thể được mở rộng qua các nhóm trọng số lớn hơn để thành các MST khác nhau.

Đây chính là phương pháp hoán đổi cạnh nhưng được thực hiện **đồng thời theo mức trọng số**, thay vì phải xây hẳn cây rồi truy vấn đường đi.

### Phát hiện chu trình trong `H_w` bằng DSU tạm

Cho mỗi nhóm cạnh trọng số w:

1. Giữ nguyên **DSU chính**, vốn mới xử lý các nhóm có trọng số nhỏ hơn w.
2. Dùng DSU chính để tìm đại diện của hai đầu từng cạnh nhóm w.
3. Nếu đại diện khác nhau, đưa cặp đại diện vào danh sách cạnh của `H_w`.
4. **Nén chỉ số** các đại diện xuất hiện trong nhóm thành các chỉ số tạm 0..k−1.
5. Tạo **DSU tạm mới**, chỉ dành cho `H_w`.
6. Với từng cạnh của `H_w`, nếu `temp.union(a,b)` trả **false**, cạnh này khép chu trình ⇒ **có nhiều MST**.
7. **Chỉ sau khi kiểm tra xong toàn nhóm**, mới duyệt những cạnh thật có trọng số w và `union` chúng vào **DSU chính** để tiếp tục Kruskal.

Điểm sống còn là **không union vào DSU chính trước khi xác định hết các cặp đại diện của cùng nhóm trọng số**. Nếu làm sớm, một cạnh có thể bị xem như “đã nối bởi cạnh nhẹ hơn” dù thực ra chỉ mới nối bởi cạnh đồng trọng số mà ta đang cần kiểm tra cạnh tranh.

## 9. Truy vết nhóm trọng số trên ví dụ

### 9.1. Tam giác đều

Khi w=2, DSU chính chưa nối hai đỉnh nào. `H_2` có ba siêu đỉnh 0,1,2 và ba cạnh:

`0−1, 1−2, 0−2`.

DSU tạm:

- union(0,1) ⇒ true.
- union(1,2) ⇒ true.
- union(0,2) ⇒ false: xuất hiện chu trình.

Kết luận **MULTIPLE**. DSU chính sau đó vẫn chạy Kruskal bình thường, chọn hai cạnh để làm một MST cụ thể.

### 9.2. Hình sao có ba cạnh trọng số 1

Ở nhóm w=1, `H_1` chính là ba cạnh:

`0−1, 0−2, 0−3`.

Tất cả union của DSU tạm đều thành công, không có chu trình: đây là một cây. DSU chính chọn cả ba cạnh, nối hết bốn đỉnh.

Đến nhóm w=3 hoặc 4, hai đầu các cạnh 1−2 và 2−3 đã nằm **trong cùng thành phần của những cạnh nhẹ hơn**, nên chúng không đi vào `H_3` hoặc `H_4`. Không có nhóm nào chứa chu trình ⇒ **UNIQUE**.

### 9.3. Hai cạnh song song

Hai cạnh có ID khác nhau cùng nối 0 và 1, trọng số 5. Ở `H_5` có **hai cạnh song song**, và:

- union tạm của cạnh thứ nhất ⇒ true.
- union tạm của cạnh thứ hai ⇒ false.

Kết luận **MULTIPLE**. Nếu khử trùng cặp (0,1) trước khi DSU tạm chạy, ta sẽ **mất thông tin** rằng có hai lựa chọn cạnh khác nhau và báo sai duy nhất.

### 9.4. Một chu trình của các cạnh cùng trọng số, thêm đường chéo nặng

Cho hình vuông:

`e₀=(0,1,1)`; `e₁=(1,2,1)`; `e₂=(2,3,1)`; `e₃=(3,0,1)`,

và đường chéo `e₄=(0,2,3)`.

Nhóm w=1 chứa chu trình bốn cạnh ⇒ nhiều MST. Mỗi MST của chu trình chọn **ba trong bốn cạnh**, tổng **3**, nên có bốn MST từ bốn cách bỏ một cạnh của chu trình. Đường chéo trọng số 3 không tạo thêm MST tối ưu. Thuật toán vẫn có thể chọn cạnh IDs [0,1,2] làm một MST để in.

## 10. Vì sao kiểm tra nhóm trọng số là đúng?

Ta chứng minh bằng bất biến của Kruskal và tính chất cắt.

**Bất biến sau khi xử lý tất cả cạnh `<w`:** DSU chính gom đúng các thành phần liên thông của đồ thị chỉ gồm những cạnh có trọng số `<w`. Dù Kruskal bỏ một số cạnh tạo chu trình, tất cả cạnh có trọng số nhỏ hơn w đã được xét; mỗi cạnh nối hai thành phần khác nhau được hợp nhất. Vì vậy DSU diễn tả chính xác kết nối có thể thực hiện bằng những cạnh nhẹ hơn.

**Vai trò của nhóm w:** sau khi co các thành phần nhỏ hơn w, tất cả cạnh có thể nối những siêu đỉnh này mà không tăng ngưỡng trọng số đều nằm trong `H_w`. Để đạt MST, ta phải dùng số cạnh tối thiểu để nối từng thành phần liên thông của `H_w` thành một thành phần trước khi cân nhắc cạnh nặng hơn. Đó là việc chọn một **rừng khung** của `H_w`.

**Nếu `H_w` là rừng:** nó không có cạnh dư; muốn nối hết những siêu đỉnh cùng thành phần ở ngưỡng w phải lấy **tất cả** cạnh của nó. Không có sự lựa chọn ở trọng số w.

**Nếu `H_w` có chu trình:** ta có thể bỏ một cạnh khác nhau trên chu trình, tạo các rừng khác nhau vẫn đạt cùng số kết nối với tổng bằng nhau. Các nhóm trọng số sau chỉ “nhìn thấy” việc các siêu đỉnh đã được nối, không phụ thuộc vào cạnh đồng trọng số nào cụ thể đã dùng, nên có thể tiếp tục thành một MST khác cùng tổng.

Quy nạp qua các nhóm w cho thấy MST duy nhất đúng khi **mọi nhóm không có chu trình**. Nếu đồ thị ban đầu **không liên thông**, cùng quy trình vẫn xác định tính duy nhất của một **rừng khung nhỏ nhất**, nhưng chương trình ở đây chủ ý báo **DISCONNECTED** vì không có MST toàn đồ thị.

### Không dùng DSU tạm chung cho các nhóm

DSU tạm của nhóm w chỉ mô phỏng chu trình **giữa các thành phần hiện thời** với cạnh đúng trọng số w. Sang nhóm w' khác phải tạo lại DSU tạm; tái dùng trạng thái cũ có thể tạo chu trình giả. DSU chính thì ngược lại: phải giữ trạng thái xuyên suốt các nhóm để ghi nhận các kết nối bằng cạnh nhẹ hơn.

## 11. Java 17+ hoàn chỉnh: Kruskal kiểm tra tính duy nhất

Chương trình sau trả một trong ba trạng thái:

- **UNIQUE:** đồ thị liên thông và chỉ có một MST theo ID cạnh.
- **MULTIPLE:** đồ thị liên thông và có nhiều MST, chương trình vẫn trả **một** tập cạnh tối ưu cụ thể.
- **DISCONNECTED:** không tồn tại MST của toàn bộ n đỉnh; `weight=none`, `edgeIds=[]`.

**Đặc điểm của triển khai:**

- Nhập số đỉnh n≥1, mọi cạnh là record `Edge(u,v,weight)` vô hướng. Mỗi cạnh được gán ID theo thứ tự trong danh sách đối số.
- Sắp tăng theo trọng số bằng `Long.compare`, phá hòa theo ID bằng `Integer.compare` để output ổn định.
- DSU chính chọn các cạnh của một MST; DSU tạm chỉ kiểm tra chu trình trong `H_w`.
- Dùng `HashMap` để nén đại diện DSU chính thành chỉ số tạm theo từng nhóm.
- **Không bỏ trùng** các cạnh song song; self-loop bị bỏ khi hai đầu thuộc cùng một thành phần.
- Dùng `BigInteger` để cộng tổng trọng số mà không tràn long, kể cả khi nhiều cạnh có trọng số âm lớn.
- Không nhận n≤0, null edges, null entry hoặc đầu mút ngoài phạm vi; dùng `IllegalArgumentException`.
- Với n=1, MST là tập cạnh rỗng có trọng số 0 và duy nhất.

Lưu thành **`UniqueMstDemo.java`**:

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class UniqueMstDemo {
    private record Edge(int u, int v, long weight) {}
    private record IndexedEdge(int id, int u, int v, long weight) {}

    private enum Status {
        UNIQUE, MULTIPLE, DISCONNECTED
    }

    private record Result(
            Status status,
            BigInteger totalWeight,
            List<Integer> edgeIds) {}

    private static final class DSU {
        final int[] parent;
        final int[] size;
        int components;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int v) {
            while (parent[v] != v) {
                parent[v] = parent[parent[v]];
                v = parent[v];
            }
            return v;
        }

        boolean union(int a, int b) {
            a = find(a);
            b = find(b);
            if (a == b) {
                return false;
            }
            if (size[a] < size[b]) {
                int temp = a;
                a = b;
                b = temp;
            }
            parent[b] = a;
            size[a] += size[b];
            components--;
            return true;
        }
    }

    // Assign a compact ID to a component representative.
    private static int compact(
            Map<Integer, Integer> map, int representative) {
        Integer existing = map.get(representative);
        if (existing != null) {
            return existing;
        }
        int next = map.size();
        map.put(representative, next);
        return next;
    }

    static Result solve(int n, Edge... inputEdges) {
        if (n <= 0 || inputEdges == null) {
            throw new IllegalArgumentException("Invalid graph size/edges");
        }

        List<IndexedEdge> edges = new ArrayList<>();
        for (int id = 0; id < inputEdges.length; id++) {
            Edge e = inputEdges[id];
            if (e == null || e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n) {
                throw new IllegalArgumentException(
                        "Invalid undirected edge");
            }
            edges.add(new IndexedEdge(
                    id, e.u(), e.v(), e.weight()));
        }

        // Never compare long weights by subtraction: it may overflow.
        edges.sort(Comparator
                .comparingLong(IndexedEdge::weight)
                .thenComparingInt(IndexedEdge::id));

        DSU main = new DSU(n);
        BigInteger total = BigInteger.ZERO;
        List<Integer> selected = new ArrayList<>();
        boolean unique = true;
        int i = 0;

        while (i < edges.size()) {
            int j = i + 1;
            long weight = edges.get(i).weight();
            while (j < edges.size()
                    && edges.get(j).weight() == weight) {
                j++;
            }

            // IMPORTANT: main DSU is still the state from weights < w.
            Map<Integer, Integer> compressed = new HashMap<>();
            List<int[]> projected = new ArrayList<>();
            for (int k = i; k < j; k++) {
                IndexedEdge e = edges.get(k);
                int rootU = main.find(e.u());
                int rootV = main.find(e.v());
                if (rootU == rootV) {
                    continue; // Already joined with cheaper edges.
                }
                int a = compact(compressed, rootU);
                int b = compact(compressed, rootV);
                projected.add(new int[] {a, b});
            }

            // Detect cycles in the contracted SAME-WEIGHT multigraph.
            DSU temporary = new DSU(compressed.size());
            for (int[] pair : projected) {
                if (!temporary.union(pair[0], pair[1])) {
                    unique = false;
                }
            }

            // Only NOW update the main DSU using this weight group.
            for (int k = i; k < j; k++) {
                IndexedEdge e = edges.get(k);
                if (main.union(e.u(), e.v())) {
                    selected.add(e.id());
                    total = total.add(
                            BigInteger.valueOf(e.weight()));
                }
            }

            i = j;
        }

        if (main.components != 1) {
            return new Result(
                    Status.DISCONNECTED, null, List.of());
        }
        return new Result(
                unique ? Status.UNIQUE : Status.MULTIPLE,
                total, List.copyOf(selected));
    }

    private static void show(String name, int n, Edge... edges) {
        Result result = solve(n, edges);
        String weight = result.totalWeight() == null
                ? "none" : result.totalWeight().toString();
        System.out.println(name + ": status=" + result.status()
                + ", weight=" + weight
                + ", edgeIds=" + result.edgeIds());
    }

    public static void main(String[] args) {
        show("Unique ties", 4,
                new Edge(0, 1, 1), new Edge(0, 2, 1),
                new Edge(0, 3, 1), new Edge(1, 2, 3),
                new Edge(2, 3, 4));

        show("Equal triangle", 3,
                new Edge(0, 1, 2), new Edge(1, 2, 2),
                new Edge(0, 2, 2));

        show("Parallel", 2,
                new Edge(0, 1, 5), new Edge(0, 1, 5));

        show("Equal square", 4,
                new Edge(0, 1, 1), new Edge(1, 2, 1),
                new Edge(2, 3, 1), new Edge(3, 0, 1),
                new Edge(0, 2, 3));

        show("Disconnected", 4,
                new Edge(0, 1, 1), new Edge(2, 3, -2));

        show("Negative weights", 3,
                new Edge(0, 1, -5), new Edge(1, 2, -2),
                new Edge(0, 2, 4));

        show("Self loop", 2,
                new Edge(0, 0, -100), new Edge(0, 1, 3));

        show("One vertex", 1,
                new Edge(0, 0, -7));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac UniqueMstDemo.java
java UniqueMstDemo
~~~

**Kết quả stdout chính xác:**

~~~text
Unique ties: status=UNIQUE, weight=3, edgeIds=[0, 1, 2]
Equal triangle: status=MULTIPLE, weight=4, edgeIds=[0, 1]
Parallel: status=MULTIPLE, weight=5, edgeIds=[0]
Equal square: status=MULTIPLE, weight=3, edgeIds=[0, 1, 2]
Disconnected: status=DISCONNECTED, weight=none, edgeIds=[]
Negative weights: status=UNIQUE, weight=-7, edgeIds=[0, 1]
Self loop: status=UNIQUE, weight=3, edgeIds=[1]
One vertex: status=UNIQUE, weight=0, edgeIds=[]
~~~

### Giải thích từng dòng

**Unique ties:** có ba cạnh cùng trọng số 1 tạo hình sao, nhưng không có cạnh nào đồng giá trị có thể thay chúng để giữ một cây khung. MST duy nhất tổng 3, IDs [0,1,2].

**Equal triangle:** ba cạnh bằng 2 tạo chu trình; bỏ bất kỳ một cạnh vẫn là cây khung tổng 4. Kruskal chọn hai ID đầu, nhưng có **3** cây tối ưu.

**Parallel:** hai cạnh trùng endpoint và trọng số nhưng có ID khác nhau. Chọn ID 0 hoặc ID 1 đều cho trọng số 5 ⇒ nhiều MST.

**Equal square:** bốn cạnh trọng số 1 tạo chu trình, mỗi cây chọn ba cạnh. Đường chéo trọng số 3 quá nặng để thuộc MST, nên tổng tối ưu 3 và nhiều MST.

**Disconnected:** hai thành phần rời nhau không thể tạo một cây chứa cả bốn đỉnh; không tồn tại MST nên weight=none, dù Kruskal nội bộ có thể chọn hai cạnh của rừng.

**Negative weights:** hai cạnh trọng số −5 và −2 đủ nối ba đỉnh, tổng −7; cạnh còn lại trọng số 4 không thể hoán đổi ngang giá. MST duy nhất.

**Self loop:** cạnh tự nối 0–0 dù trọng số −100 cũng không giúp tạo cây; cạnh 0–1 trọng số 3 là MST duy nhất. Self-loop bị bỏ hoàn toàn trong đồ thị co.

**One vertex:** một đỉnh có một self-loop âm vẫn chỉ có cây khung không cạnh, tổng 0.

### Bốn điểm quan trọng của mã

1. **Đánh số ID bằng thứ tự input.** Cạnh song song giữ ID khác nhau; `edgeIds` liệt kê những cạnh được Kruskal chọn theo thứ tự duyệt trọng số, không nhất thiết tăng dần theo ID.
2. **DSU chính chỉ ghi nhận cạnh nhẹ hơn khi kiểm tra nhóm w.** Đầu tiên tính toàn bộ đại diện và projected edges, sau đó kiểm tra DSU tạm, cuối cùng mới union DSU chính.
3. **DSU tạm phát hiện chu trình đa cạnh.** Union thất bại trong projected graph ⇒ một nhóm trọng số có các lựa chọn rừng ngang giá.
4. **Trạng thái DISCONNECTED được ưu tiên.** Nếu không có MST, không được in UNIQUE/MULTIPLE chỉ dựa vào một cờ về rừng khung.

## 12. Phân tích độ phức tạp của chương trình

Với n đỉnh và m cạnh:

- Tạo danh sách cạnh có ID: **O(m)**.
- Sắp cạnh theo (trọng số, ID): **O(m log m)** phép so sánh.
- Mọi cạnh được xét một lần khi dựng projected graph trong nhóm trọng số của nó, và một lần khi union vào DSU chính.
- Tổng phép find/union của DSU chính và DSU tạm là **O(m·α(n))**, với `α` là hàm Ackermann nghịch đảo cực chậm tăng. Số siêu đỉnh của mỗi nhóm không vượt n.
- Nén các đại diện qua `HashMap` có chi phí **O(1) kỳ vọng** mỗi thao tác ⇒ tổng **O(m) kỳ vọng**. Không khẳng định mọi truy cập HashMap đều O(1) trong trường hợp xấu đối kháng.
- Cộng trọng số vào `BigInteger` một lần trên mỗi cạnh được chọn, tối đa n−1 lần; mỗi phép cộng có chi phí phụ thuộc số bit, tránh tràn long.

Độ phức tạp theo mô hình thao tác số học và hash kỳ vọng là:

**Thời gian `O(m log m + m·α(n) + n)`; bộ nhớ `O(n+m)`.**

Khi m=0, việc khởi tạo DSU vẫn mất O(n) thời gian/bộ nhớ. Trong đồ thị đơn, `m≤n(n−1)/2`; ở **đa đồ thị**, m có thể lớn hơn vì nhiều cạnh song song.

Bản dùng tìm đường trên một MST để kiểm tra mọi non-tree edge có thể mất O(mn) nếu mỗi đường tìm bằng DFS riêng. Nếu tiền xử lý đường đi với LCA lấy max trên path, có thể làm hiệu quả hơn, nhưng vẫn phải xử lý các cạnh song song theo ID và đồ thị không liên thông.

### Vì sao không cần tính tổng trước khi kết luận nhiều MST?

Phát hiện chu trình trong `H_w` chỉ dựa trên **quan hệ lựa chọn ngang trọng số**, không cần cộng tổng trọng số. Chương trình vừa tính trạng thái duy nhất vừa dựng một MST và tổng để tiện kiểm chứng; phần uniqueness có thể dùng chung thứ tự cạnh/DSU chính mà không cần BigInteger nếu chỉ trả một boolean.

## 13. Cây khung tối ưu thứ hai có thể dựng thế nào?

Biết **MULTIPLE** trả lời câu hỏi có nhiều MST, nhưng đôi khi đề yêu cầu **in hai cây khác nhau**. Mã chính chỉ in một cây và trạng thái, vì việc xuất nhân chứng cần thêm bước.

Phương án dễ chứng minh:

1. Lấy `T` từ Kruskal và lưu ID các cạnh được chọn.
2. Xét mỗi **cạnh e không thuộc T**, bỏ self-loop.
3. Tìm đường `P_T(u,v)` trên cây.
4. Lấy cạnh f nặng nhất trên đường.
5. Nếu `w(e)=w(f)`, tạo `T'=T−f+e` và in hai danh sách ID.

**Ví dụ tam giác:** T={e₀,e₁}, non-tree edge e₂ nối 0–2. Đường trên T là 0–1–2, có hai cạnh trọng số 2. Chọn f=e₀, ta được T'={e₁,e₂}, khác T nhưng cùng tổng 4.

**Ví dụ song song:** T={e₀}, non-tree edge e₁ nối 0–1. Đường trên T gồm e₀ trọng số 5, nên đổi e₀ thành e₁ được MST khác có tổng 5.

### Một MST khác không phải “MST có tổng thứ hai”

Nếu tồn tại nhiều MST cùng tổng tối ưu, “cây thứ hai theo thứ tự các phương án” có thể vẫn có **cùng tổng** với cây thứ nhất. Một bài hỏi **second-best MST có tổng lớn hơn nghiêm ngặt** là bài toán khác: cần tìm **giá trị nhỏ nhất lớn hơn tối ưu**, không chỉ tìm cạnh hoán đổi có hiệu bằng 0.

Khi có nhiều MST đồng trọng số, đôi lúc để tìm tổng lớn hơn nhỏ nhất phải xét thay một cạnh **không phải cạnh lớn nhất** trên đường cây (nhằm tạo delta dương khi lựa chọn cạnh lớn nhất chỉ cho delta=0). Vì thế không được dùng cờ MULTIPLE thay cho lời giải second-best MST nghiêm ngặt.

## 14. Đếm số MST: khác với kiểm tra có nhiều hay không

Câu hỏi **“có nhiều MST không?”** chỉ cần biết số phương án là **1 hay lớn hơn 1**. Câu hỏi **“có chính xác bao nhiêu MST?”** khó hơn và có thể cho số rất lớn.

Ví dụ:

- Tam giác ba cạnh cùng trọng số: **3 MST**.
- Hình vuông bốn cạnh cùng trọng số, không xét đường chéo nặng: **4 MST**.
- Hai cạnh song song cùng trọng số nối hai đỉnh: **2 MST**.
- Hình sao ba cạnh trọng số 1 bị buộc: **1 MST**.

Ý tưởng mở rộng theo nhóm trọng số: tại mỗi w, sau khi co các cạnh nhẹ hơn, với mỗi thành phần liên thông của `H_w`, ta cần chọn một cây khung của thành phần ấy. **Số lựa chọn rừng khung tối ưu của nhóm** bằng tích số cây khung của các thành phần trong `H_w`. Nhân những con số ấy qua mọi nhóm w cho số MST của đồ thị gốc liên thông.

Để đếm số cây khung của một **đa đồ thị** một cách chính xác, có thể dùng **định lý Matrix–Tree** (lấy một định thức con của ma trận Laplace); cạnh song song phải được đếm với **bội số** của nó trong ma trận. Đây là một thuật toán mở rộng, có chi phí lớn hơn việc chỉ kiểm tra có chu trình và phải dùng số nguyên lớn/định thức chính xác khi kết quả lớn.

**Không được tính số MST bằng `2^k` chỉ vì có k nhóm chứa tie/cycle.** Một chu trình tam giác có 3 cách tạo cây chứ không phải 2, còn các chu trình có thể cùng chia sẻ cạnh và ràng buộc lẫn nhau.

## 15. Rừng khung nhỏ nhất và trường hợp không liên thông

Nếu đồ thị có c>1 thành phần liên thông, không có cây khung bao phủ tất cả n đỉnh. Tuy nhiên Kruskal vẫn xây một **rừng khung nhỏ nhất** có n−c cạnh: ở mỗi thành phần liên thông, nó chọn một cây khung nhỏ nhất của thành phần ấy.

Khi đề yêu cầu **MSF**:

- Cần xác định rừng tối ưu có duy nhất hay không theo ID cạnh.
- Có thể dùng cùng tiêu chí **chu trình trong `H_w`** trên các thành phần, nhưng kết quả mang nghĩa **duy nhất của MSF**, không phải MST.
- Tổng trọng số là tổng các cây khung nhỏ nhất của từng thành phần.
- Một cây khung khác trong bất kỳ thành phần nào tạo **MSF khác** với cùng tổng.

Mã minh họa cố ý không trả MSF như một MST giả: sau khi xử lý hết cạnh, nếu `main.components!=1`, nó trả trạng thái **DISCONNECTED**, trọng số và danh sách cạnh MST là không có.

**Đối với n=1**, rừng/cây chỉ gồm đỉnh duy nhất, là một MST hợp lệ theo quy ước bài; với n=0, chương trình từ chối vì định nghĩa bài học cố định n≥1.

## 16. Kiểm thử chính xác bằng vét cạn cây khung

Một bộ kiểm thử tốt phải **độc lập với Kruskal**. Với đồ thị nhỏ, n≤6 và m≤10, có thể liệt kê mọi tập con cạnh kích thước n−1. Với mỗi tập con:

1. Tạo DSU mới.
2. Chèn từng cạnh; nếu chèn một cạnh mà hai đầu đã cùng thành phần, tập con có chu trình ⇒ loại.
3. Sau n−1 cạnh, chỉ nhận nếu mọi đỉnh liên thông.
4. Tính tổng trọng số đúng (kể cả âm).
5. Giữ **giá trị tổng nhỏ nhất**, và **đếm số tập cạnh khác nhau theo ID** có tổng bằng giá trị ấy.

Kết quả oracle:

- **Không có tập con hợp lệ:** trạng thái DISCONNECTED.
- Có đúng **một** tập con đạt min: UNIQUE.
- Có **ít nhất hai** tập con đạt min: MULTIPLE.

So kết quả oracle với thuật toán nhóm trọng số, bao gồm tổng tối ưu và tính hợp lệ của `edgeIds` trả về. Một lời giải phát hiện nhiều MST bằng chính cùng thuật toán Kruskal không phải oracle đủ độc lập để bắt lỗi xử lý tie.

### Kết quả kiểm tra cụ thể

| Dữ liệu | Tối ưu | Số MST | Trạng thái |
|---|---:|---:|---|
| Hình sao nhiều cạnh 1 | 3 | 1 | UNIQUE |
| Tam giác mọi cạnh 2 | 4 | 3 | MULTIPLE |
| Hai cạnh song song trọng số 5 | 5 | 2 | MULTIPLE |
| Hình vuông cạnh 1, đường chéo 3 | 3 | 4 | MULTIPLE |
| Hai thành phần tách biệt | Không có MST | 0 | DISCONNECTED |
| Ba đỉnh có cạnh −5, −2, 4 | −7 | 1 | UNIQUE |
| Self-loop −100 và cạnh nối hai đỉnh 3 | 3 | 1 | UNIQUE |
| Một đỉnh có self-loop −7 | 0 | 1 | UNIQUE |

### Property-based và random testing

Sinh ngẫu nhiên n từ 1..6, số cạnh m từ 0..10, hai đầu mút bất kỳ (kể cả u=v), trọng số nguyên từ −8 tới 8. Cho phép cạnh song song và trọng số bằng nhau vì đó chính là phần thuật toán dễ sai.

Đối với mỗi đồ thị:

- Chạy **Kruskal + kiểm tra nhóm trọng số**.
- Liệt kê mọi tập cạnh kích thước n−1 để tính chính xác giá trị và số MST.
- Kiểm tra nếu thuật toán trả UNIQUE thì oracle có đúng một cây; MULTIPLE thì số cây≥2; DISCONNECTED thì oracle không có cây.
- Kiểm tra khi có MST, tập edgeIds của thuật toán **chứa n−1 ID khác nhau**, không có chu trình, liên thông và tổng đúng giá trị tối ưu.
- Đảo thứ tự cạnh input: **trạng thái** và **tổng tối ưu** phải không đổi, dù ID/những cạnh được chọn có thể đổi.
- Nếu tăng trọng số một cạnh đã bị bỏ vì nặng, trạng thái không nhất thiết đổi; nếu biến nó thành đồng trọng số của cạnh trên path, có thể phát sinh nhiều MST. Đây là kiểm thử nhạy với dấu bằng.

Bộ thử này bắt được lỗi mà chỉ so trọng số không thấy: một thuật toán có thể tính **đúng tổng MST** nhưng báo **UNIQUE** sai khi có chu trình gồm các cạnh đồng trọng số.

## 17. Các lỗi phổ biến

1. **Thấy hai trọng số bằng nhau rồi báo nhiều MST:** không có phép hoán đổi ngang giá thì MST vẫn duy nhất.
2. **Thấy mọi trọng số khác nhau nhưng không kiểm tra liên thông:** đồ thị không liên thông thì không có MST, không thể gọi là MST duy nhất.
3. **Coi đầu ra Kruskal cố định là bằng chứng duy nhất:** tie-break chỉ chọn một phương án.
4. **Nhìn union=false ở DSU chính rồi báo nhiều MST:** cạnh bị loại có thể **nặng hơn**, không cạnh tranh ở mức tối ưu.
5. **Union DSU chính trước khi xét hết nhóm đồng trọng số:** làm mất trạng thái kết nối bằng **cạnh nhẹ hơn**.
6. **Không tạo DSU tạm mới cho mỗi trọng số:** tạo chu trình giả xuyên nhóm.
7. **Không bỏ cạnh có hai đầu đã cùng thành phần từ các trọng số nhẹ hơn:** những cạnh ấy không là lựa chọn cùng giá để nối siêu đỉnh.
8. **Khử trùng các cạnh song song:** có thể bỏ mất nhiều MST phân biệt theo ID cạnh.
9. **Tính self-loop như cạnh nối hai thành phần:** self-loop không thể thuộc cây khung.
10. **So sánh trọng số bằng phép trừ long:** hiệu có thể tràn, làm sắp cạnh sai.
11. **Cộng tổng trọng số lớn bằng long không chứng minh giới hạn:** có thể tràn; dùng BigInteger hoặc kiểm tra giới hạn.
12. **Quên n=1:** cây không có cạnh là MST duy nhất.
13. **Mặc định n=0 là một MST theo cách của chương trình này:** API đã từ chối n≤0.
14. **Nhầm trọng số của một cạnh với tổng MST:** nhiều cây có thể cùng tổng dù từng edge ID khác nhau.
15. **Kiểm tra non-tree edge e bằng min trên đường T thay vì max:** công thức đúng cần `M_T(u,v)=max w(f)`.
16. **Không bỏ self-loop khi kiểm tra path exchange:** path(u,u) rỗng, không có cạnh để thay.
17. **Nếu w(e)<maxPath mà vẫn khẳng định T tối ưu:** tìm được cây nhẹ hơn T.
18. **Đếm số MST bằng số lần gặp union=false:** union=false chỉ phát hiện **có chu trình**, không đếm số cây khung.
19. **Cho rằng ID của các cạnh được chọn luôn tăng dần:** mã chọn theo (weight, ID), không theo ID toàn cục.
20. **Dùng trạng thái MULTIPLE để trả lời “MST lớn hơn nghiêm ngặt thứ hai”**: cần một bài toán giá trị khác.
21. **Dùng điều kiện cut “có vài cạnh đồng hạng nhẹ nhất ⇒ tất cả bắt buộc”:** chỉ **nhẹ nhất nghiêm ngặt** mới có bảo đảm thuộc mọi MST theo định lý nêu trên.
22. **Quên rằng đồ thị đa cạnh có chu trình hai cạnh song song:** DSU tạm có thể phát hiện nó qua lần union thứ hai.
23. **Coi rừng khung của đồ thị rời là MST:** chỉ khi đề nói MSF mới được trả rừng.
24. **Suy ra số MST bằng cách nhân số cách tùy tiện ở những chu trình giao nhau:** muốn đếm chính xác cần phân tích `H_w` theo thành phần, có thể dùng Matrix–Tree.

## 18. Checklist trước khi nộp lời giải

- Bài yêu cầu một **MST**, kiểm tra **duy nhất**, xuất **hai MST** hay **đếm số MST**?
- Đồ thị là **vô hướng** và có **liên thông** không? Nếu không, đã phân biệt MST với MSF chưa?
- Cạnh song song có ID riêng và được tính là các phương án khác nhau không?
- Self-loop có bị loại khỏi mọi cây khung không?
- Có biết **trọng số phân biệt là đủ nhưng không cần** cho MST duy nhất không?
- Tính chất cut/cycle có dùng đúng từ **nhỏ nhất duy nhất** và **lớn nhất duy nhất** không?
- Nếu có MST T, với mỗi non-tree edge e đã hiểu tiêu chí `w(e)=maxPathWeight_T(u,v)` chưa?
- Nếu kiểm tra theo Kruskal, có sắp cạnh theo trọng số tăng bằng comparator **không tràn** không?
- Khi xét một nhóm w, DSU chính có còn phản ánh **chỉ những cạnh nhẹ hơn w** không?
- Có co các thành phần nhẹ hơn và giữ **mọi cạnh đồng trọng số** nối các siêu đỉnh khác nhau không?
- DSU tạm có được tạo **mới trong mỗi nhóm w** và có phát hiện chu trình do cạnh song song không?
- DSU chính chỉ union **sau khi kiểm tra xong nhóm** không?
- Trạng thái DISCONNECTED có được ưu tiên trước khi kết luận UNIQUE/MULTIPLE không?
- Một MST xuất ra có đúng n−1 cạnh, liên thông, không chu trình và tổng bằng tối ưu không?
- Tổng trọng số có thể tràn số nguyên không? Đã dùng kiểu phù hợp chưa?
- Nếu đề cần hai cây, có thể dựng cây thứ hai bằng một phép **hoán đổi cạnh bằng trọng số** không?
- Nếu đề cần đếm số MST, đã tách khỏi bài boolean và xem xét các thành phần của `H_w` chưa?
- Đã đối chiếu với **vét cạn tất cả cây khung nhỏ** để kiểm tra cả tính duy nhất, không chỉ tổng trọng số chưa?

**Kết luận:** tính duy nhất của MST không phụ thuộc đơn giản vào việc “có trọng số trùng hay không”, mà phụ thuộc việc **có thể hoán đổi những cạnh cùng chi phí mà vẫn giữ cây khung tối ưu hay không**. Với một MST T, dấu bằng **`w(e)=max_{f∈P_T(e)}w(f)`** cho một non-tree edge chính là chứng cứ có MST thứ hai. Trong Kruskal, cùng hiện tượng ấy xuất hiện thành **chu trình trong đồ thị đa cạnh của từng nhóm trọng số sau khi co các thành phần nối bằng cạnh nhẹ hơn**. Kiểm tra cả nhóm đồng trọng số trước khi union vào DSU chính cho một thuật toán gần chi phí Kruskal thông thường; kết quả phải được phân biệt rõ thành **UNIQUE**, **MULTIPLE** hoặc **DISCONNECTED**.