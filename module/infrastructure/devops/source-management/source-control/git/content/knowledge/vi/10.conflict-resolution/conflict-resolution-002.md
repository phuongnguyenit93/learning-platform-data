# Đọc dấu xung đột với merge, diff3 và zdiff3

Khi Git không thể tự kết hợp hai thay đổi, Git giữ lại nội dung của các phía và đánh dấu vùng cần người phát triển quyết định. Những dòng như **<<<<<<<**, **=======** và **>>>>>>>** là dấu xung đột. Chúng cho biết phần nội dung đang bất đồng, nhưng không nói phần nào đúng về mặt nghiệp vụ.

Trong chương **Giải quyết xung đột** của module **SOURCE_CONTROL_GIT**, bài học này tập trung vào cách đọc ba kiểu trình bày xung đột: **merge**, **diff3** và **zdiff3**. Hiểu được các dấu này giúp ta lần theo thay đổi của từng nhánh, nhìn lại nội dung gốc trước khi chỉnh sửa và đưa ra một kết quả hợp nhất có chủ đích.

Sau bài học, bạn có thể:

- Nhận diện phần thay đổi của nhánh hiện tại, nhánh được hợp nhất và phiên bản gốc.
- Giải thích sự khác nhau giữa ba kiểu conflict marker.
- Chọn kiểu hiển thị phù hợp và cấu hình Git cho một repository hoặc toàn bộ máy.
- Đọc các phiên bản đang nằm trong index khi cần điều tra một xung đột khó.
- Hoàn tất việc giải quyết xung đột và tiếp tục đúng thao tác merge, rebase hoặc cherry-pick.

## 1. Vì sao Git tạo dấu xung đột?

Git thường kết hợp thay đổi bằng cách so sánh ba phiên bản:

1. **Base (merge base)**: phiên bản chung gần nhất mà hai nhánh cùng phát triển từ đó.
2. **Ours**: phiên bản ở phía đang được checkout, tức phía hiện tại của thao tác hợp nhất.
3. **Theirs**: phiên bản ở phía được đưa vào, chẳng hạn nhánh mà ta đang merge.

Git có thể tự kết hợp khi các thay đổi không chồng lấn hoặc khi kết quả có thể suy ra rõ ràng. Xung đột xuất hiện khi hai phía cùng thay đổi một vùng theo những cách không thể tự động dung hòa, hoặc khi cấu trúc thay đổi khiến Git không thể xác định kết quả an toàn.

Ví dụ, base có quy tắc tính phí:

~~~java
return amount * 0.03;
~~~

Nhánh hiện tại đổi thành:

~~~java
return amount * 0.05;
~~~

Trong khi nhánh được merge đổi cùng dòng thành:

~~~java
return amount * 0.04;
~~~

Git không biết quy tắc 5% hay 4% mới phản ánh quyết định sản phẩm. Nó đánh dấu vùng xung đột để người phát triển xem xét. Việc chọn một phía, kết hợp cả hai hoặc viết một cách triển khai thứ ba phải dựa trên yêu cầu của ứng dụng.

Các conflict marker được ghi vào working tree của file văn bản. Đồng thời, index giữ các phiên bản chưa hợp nhất ở những stage riêng. Vì vậy, marker là cách Git trình bày xung đột để con người xử lý; chúng không phải là một quyết định đã được Git đưa ra.

## 2. Kiểu mặc định merge: đọc hai phía thay đổi

Kiểu **merge** là cách trình bày ngắn gọn và thường là mặc định. Một vùng xung đột có dạng:

~~~text
<<<<<<< HEAD
return amount * 0.05;
=======
return amount * 0.04;
>>>>>>> feature/minimum-fee
~~~

Đọc từ trên xuống:

| Dấu | Ý nghĩa |
| --- | --- |
| **<<<<<<< HEAD** | Bắt đầu phần nội dung ở phía ours. Trong một lần merge thông thường, đây là nội dung từ HEAD, tức nhánh hiện tại. |
| Các dòng trước **=======** | Nội dung của phía ours. |
| **=======** | Ranh giới giữa hai phía. |
| Các dòng sau **=======** | Nội dung của phía theirs. |
| **>>>>>>> feature/minimum-fee** | Kết thúc vùng xung đột; nhãn cho biết phía theirs trong ví dụ này. |

Tên sau các dấu mở và đóng có thể là tên nhánh, tên commit hoặc nhãn do Git tạo ra. Không nên chỉ dựa vào chuỗi nhãn để suy luận toàn bộ lịch sử; hãy kết hợp nó với thao tác đang thực hiện và trạng thái repository.

Kiểu **merge** cho biết hai phiên bản đang bất đồng nhưng **không hiển thị phiên bản base**. Nếu chỉ cần chọn giữa hai thay đổi đã hiểu rõ, dạng ngắn này thường dễ đọc. Nếu chưa rõ vì sao hai phía đi đến hai kết quả khác nhau, thiếu phần base có thể khiến ta phải mở lịch sử hoặc truy xuất phiên bản gốc bằng lệnh khác.

## 3. Kiểu diff3: xem cả nội dung gốc

Kiểu **diff3** bổ sung phần base vào giữa hai phía. Cùng ví dụ tính phí, vùng xung đột có thể được trình bày như sau:

~~~text
<<<<<<< HEAD
return amount * 0.05;
||||||| <merge-base>
return amount * 0.03;
=======
return amount * 0.04;
>>>>>>> feature/minimum-fee
~~~

Dấu **|||||||** mở phần nội dung gốc. Nhãn đi sau dấu này có thể nhận diện merge base hoặc phiên bản gốc mà Git dùng để so sánh. Phần này nằm giữa ours và theirs:

- Từ **<<<<<<<** đến trước **|||||||**: nội dung phía ours.
- Từ **|||||||** đến trước **=======**: nội dung trong base.
- Từ **=======** đến trước **>>>>>>>**: nội dung phía theirs.

Base trả lời một câu hỏi quan trọng: **trước khi hai nhánh thay đổi, nội dung tại vùng này là gì?** Trong ví dụ trên, ta biết cả hai nhánh đều thay đổi mức phí từ 3%, một bên thành 5% và bên kia thành 4%. Điều đó giúp phân biệt thay đổi mới với hành vi vốn đã tồn tại.

Hãy dùng thông tin base để tìm hiểu ý định thay đổi, không mặc định chọn base làm kết quả. Base là trạng thái lịch sử chung; nó có thể đã lỗi thời hoặc chính là hành vi mà cả hai nhánh đang muốn thay thế.

Một ví dụ có nhiều dòng giúp thấy rõ hơn:

**Base**

~~~java
if (enabled) {
    return legacyPolicy();
}
~~~

**Ours**

~~~java
if (enabled) {
    audit();
    return fastPolicy();
}
~~~

**Theirs**

~~~java
if (enabled) {
    return safePolicy();
}
~~~

Một vùng xung đột theo kiểu **diff3** có thể cho thấy cả ba phiên bản:

~~~text
<<<<<<< HEAD
if (enabled) {
    audit();
    return fastPolicy();
}
||||||| <merge-base>
if (enabled) {
    return legacyPolicy();
}
=======
if (enabled) {
    return safePolicy();
}
>>>>>>> feature/safe-policy
~~~

Nhìn vào ba phần, ta thấy ours bổ sung thao tác audit và đổi chính sách sang fast; theirs đổi chính sách sang safe. Người giải quyết cần kiểm tra yêu cầu thực tế: có phải vẫn cần audit không, chính sách nào đúng, và hai thay đổi có thể kết hợp thành một cách triển khai mới hay không.

## 4. Kiểu zdiff3: giữ base nhưng thu gọn vùng xung đột

Kiểu **zdiff3** cũng hiển thị base như **diff3**, đồng thời đưa các dòng chung ở đầu hoặc cuối vùng xung đột ra ngoài các marker khi có thể. Nhờ vậy, phần cần tập trung xử lý thường ngắn hơn và các dòng ngữ cảnh giống nhau không bị lặp lại trong từng phía.

Với ví dụ chính sách ở trên, cách trình bày theo ý tưởng của **zdiff3** có thể trông như sau:

~~~text
if (enabled) {
<<<<<<< HEAD
    audit();
    return fastPolicy();
||||||| <merge-base>
    return legacyPolicy();
=======
    return safePolicy();
>>>>>>> feature/safe-policy
}
~~~

Hai dòng cấu trúc chung **if (enabled) {** và **}** nằm ngoài vùng marker. Phần được đánh dấu tập trung vào các dòng khác nhau giữa ba phiên bản. Đây là minh họa cho cách thu gọn; ranh giới thực tế phụ thuộc vào nội dung và cách Git phân tích vùng khác biệt.

Điểm cần nhớ:

- **zdiff3** vẫn cung cấp ba góc nhìn: ours, base và theirs.
- Những dòng chung được đưa ra ngoài marker vẫn là một phần của file và thường vẫn cần giữ trong kết quả.
- Việc thu gọn chỉ thay đổi cách hiển thị vùng xung đột; nó không tự chọn chính sách hoặc tự giải quyết bất đồng.

## 5. So sánh ba kiểu conflict marker

| Kiểu | Hiển thị ours | Hiển thị base | Hiển thị theirs | Đặc điểm |
| --- | --- | --- | --- | --- |
| **merge** | Có | Không | Có | Ngắn gọn, dễ xem khi hai phía đã rõ. |
| **diff3** | Có | Có | Có | Cho biết nội dung trước khi hai phía thay đổi; vùng hiển thị có thể dài hơn. |
| **zdiff3** | Có | Có | Có | Có thông tin base và thu gọn các dòng chung ở biên vùng xung đột khi có thể. |

Có thể chọn theo nhu cầu:

- Dùng **merge** khi xung đột nhỏ, hai thay đổi dễ hiểu và không cần xem lại trạng thái gốc.
- Dùng **diff3** khi cần điều tra vì sao hai phía xung đột hoặc cần so sánh rõ ba phiên bản.
- Dùng **zdiff3** khi muốn giữ thông tin base nhưng giảm phần lặp, đặc biệt với những vùng thay đổi có nhiều dòng chung ở biên.

Với công việc giải quyết xung đột thường xuyên, **zdiff3** là lựa chọn hữu ích nếu phiên bản Git đang dùng hỗ trợ. Trong nhóm, nên thống nhất kiểu hiển thị để các thành viên dễ trao đổi về cùng một vùng xung đột. Dù chọn kiểu nào, kết quả cuối cùng vẫn phải dựa trên ý định của thay đổi và kiểm thử của dự án.

## 6. Cấu hình kiểu hiển thị trong Git

Có thể đặt kiểu conflict marker ở nhiều phạm vi.

**Chỉ áp dụng cho repository hiện tại**

~~~bash
git config --local merge.conflictStyle zdiff3
~~~

**Áp dụng mặc định cho các repository của người dùng hiện tại**

~~~bash
git config --global merge.conflictStyle zdiff3
~~~

**Kiểm tra giá trị và nguồn cấu hình**

~~~bash
git config --show-origin --get merge.conflictStyle
~~~

Nếu lệnh không trả về giá trị, repository có thể đang dùng mặc định của Git. Có thể xem phiên bản Git bằng:

~~~bash
git --version
~~~

Để chỉ định kiểu cho một lần merge, dùng tùy chọn:

~~~bash
git merge --conflict=diff3 feature/minimum-fee
~~~

Hoặc đặt cấu hình tạm thời cho riêng lệnh:

~~~bash
git -c merge.conflictStyle=zdiff3 merge feature/minimum-fee
~~~

Tham số **--conflict** cho phép chọn kiểu trình bày cho lần merge đó. Cấu hình **merge.conflictStyle** giúp đặt mặc định cho các thao tác phù hợp về sau. Nếu đang có xung đột và muốn xem lại cùng nội dung theo một kiểu khác, hãy kiểm tra trạng thái file trước khi yêu cầu Git dựng lại phiên bản xung đột; thao tác khôi phục file có thể ghi đè phần chỉnh sửa chưa lưu của bạn.

## 7. Kiểm tra các phiên bản xung đột trong index

Khi marker không đủ để giải thích một tình huống phức tạp, có thể đọc các stage chưa hợp nhất trong index.

~~~bash
git ls-files -u -- src/Fee.java
~~~

Với một file xung đột thông thường, Git có thể lưu ba phiên bản:

| Stage | Nội dung |
| --- | --- |
| **1** | Base, phiên bản chung trước khi hai phía thay đổi. |
| **2** | Ours, phiên bản phía hiện tại của thao tác hợp nhất. |
| **3** | Theirs, phiên bản phía được đưa vào. |

Có thể xem từng phiên bản bằng:

~~~bash
git show :1:src/Fee.java
git show :2:src/Fee.java
git show :3:src/Fee.java
~~~

Nếu file được thêm độc lập ở cả hai phía, có thể không tồn tại stage 1 vì không có phiên bản base tương ứng. Các dạng xung đột như xóa/sửa hoặc đổi tên cũng có thể khiến cấu trúc stage khác với trường hợp sửa cùng một file. Vì vậy, đừng giả định lúc nào cũng có đủ cả ba stage.

Các lệnh diff sau giúp so sánh file đang giải quyết với từng phiên bản:

~~~bash
git diff --base -- src/Fee.java
git diff --ours -- src/Fee.java
git diff --theirs -- src/Fee.java
git diff --cc -- src/Fee.java
~~~

**--base**, **--ours** và **--theirs** lần lượt giúp xem khác biệt so với phiên bản gốc, phía hiện tại và phía được đưa vào. **--cc** hiển thị combined diff cho nội dung đang xung đột. Những lệnh này hữu ích khi file dài hoặc marker đã bị chỉnh sửa trong quá trình giải quyết.

## 8. Quy trình đọc và giải quyết một vùng xung đột

Hãy xử lý từng file và từng vùng xung đột theo một quy trình có thể kiểm tra lại.

### Bước 1: xác định thao tác đang dừng

~~~bash
git status
git diff -- src/Fee.java
~~~

Đọc thông báo của Git để biết đang merge, rebase hay cherry-pick. Điều này quan trọng vì cách hiểu ours và theirs thay đổi theo thao tác.

### Bước 2: đọc đủ ba phần nếu có

Với kiểu **diff3** hoặc **zdiff3**, đọc lần lượt ours, base và theirs. Tự trả lời:

- Nội dung gốc đang làm gì?
- Mỗi phía đã thay đổi điều gì?
- Hai thay đổi có cùng mục tiêu hay đang theo hai quy tắc nghiệp vụ khác nhau?
- Có dòng chung nào đang nằm ngoài vùng marker và cần được giữ lại không?

Nếu repository đang dùng kiểu **merge**, hãy dùng lịch sử commit, **git show** hoặc các lệnh xem stage để tìm hiểu base khi cần.

### Bước 3: quyết định kết quả theo ý định

Không chọn ours chỉ vì đó là phần đầu, cũng không chọn theirs chỉ vì phần cuối. Một số kết quả hợp lệ có thể là:

- Giữ thay đổi của một phía vì phía kia đã lỗi thời.
- Kết hợp hai thay đổi nếu chúng bổ sung cho nhau.
- Viết lại đoạn mã theo thiết kế mới, đồng thời bảo toàn các hành vi cần thiết từ cả hai phía.

Ví dụ, nếu một phía thêm audit còn phía kia đổi chính sách tính phí, kết quả có thể cần giữ audit và dùng chính sách đã được nhóm thống nhất. Marker chỉ giúp nhận ra khác biệt; yêu cầu sản phẩm, hợp đồng API và kiểm thử mới xác định kết quả đúng.

### Bước 4: chỉnh sửa file

Sau khi quyết định, chỉnh file thành nội dung cuối cùng. Xóa các dòng marker còn sót lại:

- **<<<<<<< ...**
- **||||||| ...** nếu đang dùng **diff3** hoặc **zdiff3**
- **=======**
- **>>>>>>> ...**

Không xóa nhầm các dòng mã nằm ngoài marker. Với **zdiff3**, các dòng chung đã được đưa ra ngoài vùng xung đột vẫn có thể là phần cần thiết của chương trình.

### Bước 5: kiểm tra và đánh dấu đã giải quyết

~~~bash
git diff -- src/Fee.java
git add -- src/Fee.java
git status
git diff --cached -- src/Fee.java
git diff --cached --check
~~~

**git add** thông báo với Git rằng file đã được giải quyết và đưa nội dung hiện tại vào index. Git không đảm bảo rằng bạn đã xóa mọi chuỗi marker hoặc chọn đúng logic nghiệp vụ; vì vậy hãy đọc lại diff đã stage và chạy các kiểm thử liên quan. **git diff --cached --check** giúp phát hiện một số lỗi khoảng trắng trong thay đổi đã stage.

### Bước 6: tiếp tục hoặc hủy thao tác khi cần

Khi tất cả file đã được giải quyết và kiểm tra, tiếp tục theo thao tác đang thực hiện:

~~~bash
git merge --continue
git rebase --continue
git cherry-pick --continue
~~~

Chỉ chạy lệnh tương ứng với thao tác đang dừng. Nếu quyết định quay lại trạng thái trước thao tác, các lệnh hủy tương ứng là:

~~~bash
git merge --abort
git rebase --abort
git cherry-pick --abort
~~~

Hủy thao tác sẽ khôi phục trạng thái trước quá trình đó theo khả năng của Git; hãy đọc trạng thái repository và bảo toàn các chỉnh sửa độc lập trước khi thực hiện.

## 9. Những nhầm lẫn thường gặp

### Ours và theirs có luôn mang cùng một ý nghĩa không?

Không. Trong một lần merge thông thường, ours là nhánh hiện tại và theirs là nhánh được merge vào. Trong rebase, góc nhìn dễ gây nhầm: Git đang phát lại commit của nhánh làm việc lên một nền mới, vì vậy phía ours thường là nền hiện tại đã được rebase lên, còn phía theirs là commit đang được phát lại. Khi gặp xung đột, hãy đọc thông báo thao tác và kiểm tra stage của index thay vì đoán chỉ từ tên **ours** hoặc **theirs**.

### Phần base có phải là đáp án nên chọn không?

Không. Base chỉ cho biết trạng thái chung trước khi hai nhánh thay đổi. Nếu cả hai phía đều sửa một lỗi hoặc cập nhật yêu cầu mới, base có thể là phiên bản không còn phù hợp.

### zdiff3 có làm Git ít xung đột hơn không?

Không. **zdiff3** làm vùng marker gọn hơn bằng cách đưa các dòng chung ở biên ra ngoài vùng được đánh dấu. Nó không thay đổi ý định của hai nhánh và không biến một xung đột logic thành kết quả tự động an toàn.

### Có phải mọi xung đột đều xuất hiện dưới dạng marker trong file?

Không. Marker văn bản phù hợp với nội dung mà Git có thể trình bày như văn bản. Xung đột nhị phân, xung đột đổi tên hoặc một số tình huống ở cấp đường dẫn cần cách xử lý khác. Hãy bắt đầu bằng **git status** để biết Git đang yêu cầu giải quyết loại xung đột nào.

### git add có chứng minh file đã đúng không?

Không. **git add** chỉ đưa nội dung hiện tại vào index và đánh dấu đường dẫn đã được giải quyết. Git vẫn có thể tạo commit chứa marker còn sót hoặc logic sai nếu người phát triển không kiểm tra. Cần xem diff, chạy kiểm thử và rà lại hành vi mong muốn trước khi tiếp tục.

## 10. Tự kiểm tra cách đọc marker

Giả sử một file cấu hình có ba phiên bản:

**Base**

~~~text
retry = 2
~~~

**Ours**

~~~text
retry = 3
~~~

**Theirs**

~~~text
retry = 5
~~~

Một vùng marker theo kiểu **diff3**:

~~~text
<<<<<<< HEAD
retry = 3
||||||| <merge-base>
retry = 2
=======
retry = 5
>>>>>>> feature/retry-policy
~~~

Hãy tự trả lời:

1. Giá trị nào thuộc base?
2. Giá trị nào thuộc ours và theirs?
3. Marker cho biết Git có thể tự quyết định số lần retry hay không?
4. Nếu nhóm muốn retry theo một chính sách mới, có thể giải quyết bằng cách viết giá trị khác ba giá trị trên hay không?

**Gợi ý:** base là 2, ours là 3 và theirs là 5. Marker cho thấy hai phía cùng thay đổi một giá trị, nhưng không cho biết số lần retry nào phù hợp. Nếu yêu cầu mới quy định một giá trị khác, người giải quyết có thể viết kết quả theo chính sách đó, sau đó kiểm tra cấu hình, kiểm thử và tài liệu liên quan.

## Kết luận

Hãy đọc conflict marker như một bản tường thuật ngắn về ba phiên bản của cùng một vùng nội dung. **merge** cho thấy hai phía thay đổi; **diff3** bổ sung trạng thái gốc; **zdiff3** giữ thông tin gốc và thu gọn các dòng chung ở biên vùng xung đột. Khi hiểu đúng từng phần, bạn có thể xác định thay đổi nào cần giữ, kết hợp hoặc viết lại, rồi xác nhận kết quả bằng diff và kiểm thử trước khi tiếp tục lịch sử Git.
