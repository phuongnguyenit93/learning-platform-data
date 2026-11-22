# Tìm commit thêm hoặc xóa nội dung bằng git log -S và -G

Khi một hàm, biến cấu hình hoặc thông báo lỗi xuất hiện trong code, bạn có thể cần biết commit nào đã thêm nó, thay đổi cách dùng hoặc xóa nó. Đọc từng commit trong lịch sử là cách chậm và dễ bỏ sót. Git cung cấp hai bộ lọc tìm thay đổi nội dung trong lịch sử: **`git log -S`** và **`git log -G`**.

Hai tùy chọn này thường được gọi là *pickaxe*. Chúng tìm commit dựa trên nội dung diff thay vì chỉ dựa vào tên tác giả, ngày tháng hoặc commit message. Điểm khác biệt quan trọng là:

- `-S<string>` tìm commit làm thay đổi **số lần xuất hiện** của chuỗi trong nội dung tệp.
- `-G<regex>` tìm commit có dòng được thêm hoặc xóa **khớp biểu thức chính quy**.

Hiểu đúng khác biệt giúp bạn chọn bộ lọc phù hợp, tìm được commit thêm/xóa một biểu thức, lần theo quá trình đổi tên API hoặc xác định khi nào một điều kiện logic bị thay đổi.

## 1. Tìm thay đổi nội dung trong lịch sử

### 1.1. git log thông thường tìm commit theo lịch sử

Lệnh cơ bản:

~~~bash
git log --oneline
~~~

hiển thị các commit có thể truy cập từ HEAD. Có thể giới hạn số lượng:

~~~bash
git log --oneline -10
~~~

Khi biết khoảng thời gian, tác giả hoặc nhánh, bạn có thể dùng các bộ lọc tương ứng. Tuy nhiên, để tìm commit có thêm hoặc xóa một đoạn code cụ thể, tìm theo nội dung diff thường hiệu quả hơn.

### 1.2. git log -S và -G là bộ lọc pickaxe

Cú pháp tổng quát:

~~~bash
git log -S'<chuỗi>' [các-tùy-chọn] [-- <pathspec>]
git log -G'<biểu-thức-chính-quy>' [các-tùy-chọn] [-- <pathspec>]
~~~

Ví dụ:

~~~bash
git log --oneline -S'calculateTax' -- src/
git log --oneline -G'calculateTax\(' -- src/
~~~

Hai lệnh đều tìm trong lịch sử các commit liên quan đến nội dung có chứa tên hàm `calculateTax`, nhưng điều kiện chọn commit khác nhau.

### 1.3. Chúng tìm trong lịch sử, không tìm toàn bộ working tree

`git log -S` và `git log -G` xét các diff giữa các commit trong phạm vi lịch sử được chọn. Chúng không đơn thuần tìm chuỗi trong các file hiện tại trên đĩa.

Nếu chỉ muốn tìm nội dung trong working tree hiện tại, dùng:

~~~bash
git grep 'calculateTax'
~~~

Nếu muốn tìm commit đã làm thay đổi nội dung, dùng pickaxe:

~~~bash
git log -S'calculateTax' -- src/
~~~

Hai mục tiêu này khác nhau:

| Nhu cầu | Công cụ |
| --- | --- |
| Tìm chuỗi trong snapshot hiện tại | `git grep` |
| Tìm commit làm thay đổi số lần xuất hiện của chuỗi | `git log -S` |
| Tìm commit có dòng thêm/xóa khớp regex | `git log -G` |
| Tìm commit theo message | `git log --grep` |
| Tìm commit cuối cùng sửa một dòng cụ thể | `git blame` |

## 2. Hiểu chính xác git log -S

### 2.1. -S kiểm tra số lần xuất hiện thay đổi

`-S<string>` chọn các commit mà số lần xuất hiện của chuỗi chỉ định thay đổi giữa phiên bản trước và sau commit.

Ví dụ, trước commit, file có:

~~~java
boolean enabled = featureEnabled();
return enabled;
~~~

Sau commit, file có:

~~~java
boolean enabled = featureEnabled();
audit(featureEnabled());
return enabled;
~~~

Chuỗi `featureEnabled` xuất hiện một lần trước commit và hai lần sau commit. Vì số lần xuất hiện thay đổi, lệnh:

~~~bash
git log -S'featureEnabled' -- src/
~~~

có thể tìm thấy commit đó.

### 2.2. Tìm commit thêm một chuỗi

Nếu muốn biết khi nào một hàm lần đầu được thêm vào:

~~~bash
git log --all --oneline -S'calculateTax' -- src/
~~~

Kết quả gồm những commit làm số lần xuất hiện của `calculateTax` thay đổi trong các đường dẫn được chọn và các ref mà Git đang tìm.

Để xem patch của các commit phù hợp:

~~~bash
git log --all -p -S'calculateTax' -- src/
~~~

Đọc patch để xác định commit nào thực sự thêm hàm, commit nào đổi cách gọi hoặc chỉ thêm/xóa một lần xuất hiện khác.

### 2.3. Tìm commit xóa một chuỗi

Nếu một điều kiện hoặc hàm bị xóa, số lần xuất hiện của chuỗi giảm. Ví dụ:

~~~bash
git log --all -p -S'legacyAuthorization' -- src/
~~~

Các commit xóa lần xuất hiện cuối cùng của `legacyAuthorization` có thể xuất hiện trong kết quả. Nếu chuỗi vẫn còn ở một vị trí khác và tổng số lần xuất hiện không đổi, commit xóa một dòng có chuỗi đó có thể không được `-S` chọn.

### 2.4. -S không chỉ tìm commit thêm mới

Tên gọi "pickaxe string" dễ khiến người học nghĩ `-S` chỉ tìm lần thêm chuỗi. Thực tế, nó tìm thay đổi về số lượng xuất hiện:

- Tăng từ 0 lên 1: thêm.
- Tăng từ 2 lên 3: thêm một lần xuất hiện.
- Giảm từ 1 xuống 0: xóa.
- Giảm từ 4 xuống 2: xóa hai lần xuất hiện.
- Giữ nguyên số lượng: không được chọn chỉ vì số lượng.

Vì vậy, `-S` phù hợp khi bạn quan tâm một token hoặc biểu thức có được thêm vào hay biến mất khỏi nội dung.

### 2.5. Khi chuỗi xuất hiện được giữ nguyên số lượng

Giả sử commit thay đổi:

~~~java
return validateAddress(input);
~~~

thành:

~~~java
boolean valid = validateAddress(input);
return valid;
~~~

Chuỗi `validateAddress` vẫn xuất hiện đúng một lần trước và sau. Số lần xuất hiện không đổi, nên:

~~~bash
git log -S'validateAddress' -- src/
~~~

có thể không trả về commit này.

Đây là giới hạn quan trọng của `-S`: nó theo dõi số lần xuất hiện, không phải mọi dòng có chứa chuỗi đã bị sửa.

## 3. Hiểu chính xác git log -G

### 3.1. -G tìm dòng được thêm hoặc xóa khớp regex

`-G<regex>` chọn commit có dòng được thêm hoặc xóa khớp biểu thức chính quy. Nó xét các dòng thay đổi trong diff.

Ví dụ:

~~~bash
git log --all --oneline -G'validateAddress' -- src/
~~~

Lệnh tìm các commit có dòng thêm hoặc xóa chứa `validateAddress`.

Để xem các dòng thay đổi:

~~~bash
git log --all -p -G'validateAddress' -- src/
~~~

### 3.2. -G bắt được thay đổi dù số lần xuất hiện không đổi

Với ví dụ:

~~~diff
- return validateAddress(input);
+ boolean valid = validateAddress(input);
+ return valid;
~~~

Số lần xuất hiện của `validateAddress` vẫn là một, nên `-S` mặc định có thể bỏ qua commit. Nhưng dòng cũ bị xóa và dòng mới được thêm đều chứa `validateAddress`, vì vậy:

~~~bash
git log -G'validateAddress' -- src/
~~~

có thể tìm thấy commit.

### 3.3. -G có thể tìm thay đổi về cách dùng

Giả sử bạn muốn tìm commit đã thay đổi cách truyền tham số cho hàm:

~~~diff
- sendRequest(url, timeout);
+ sendRequest(url, timeout, retryPolicy);
~~~

Dùng:

~~~bash
git log -G'sendRequest\(' -p -- src/
~~~

Lệnh tìm các commit có dòng thêm/xóa khớp biểu thức gọi hàm. Đọc patch để thấy tham số nào đã thay đổi.

### 3.4. -G không tìm mọi dòng chỉ vì regex xuất hiện trong file

Nếu một dòng chứa `validateAddress` không thay đổi trong commit, nó là context chứ không phải dòng được thêm hoặc xóa. Chỉ có mặt trong file không đủ để làm commit được chọn.

Đây là khác biệt với `git grep`, vốn tìm nội dung hiện tại bất kể dòng đó có thay đổi trong commit nào hay không.

## 4. So sánh -S và -G bằng cùng một ví dụ

### 4.1. Trường hợp số lần xuất hiện thay đổi

Trước:

~~~java
return checkPermission(user);
~~~

Sau:

~~~java
if (!checkPermission(user)) {
    throw new AccessDeniedException();
}
return true;
~~~

Số lần xuất hiện của `checkPermission` không đổi (một lần), nhưng dòng chứa nó đã thay đổi.

- `-S'checkPermission'`: có thể không tìm thấy commit vì số lần xuất hiện vẫn là một.
- `-G'checkPermission'`: có thể tìm thấy commit vì các dòng thêm/xóa khớp regex.

### 4.2. Trường hợp số lần xuất hiện tăng

Trước:

~~~java
if (featureEnabled()) {
    startFeature();
}
~~~

Sau:

~~~java
if (featureEnabled()) {
    audit(featureEnabled());
    startFeature();
}
~~~

Số lần xuất hiện tăng từ một lên hai.

- `-S'featureEnabled'`: tìm thấy commit.
- `-G'featureEnabled'`: cũng có thể tìm thấy commit vì dòng thêm có regex phù hợp.

### 4.3. Bảng chọn công cụ

| Tình huống | -S | -G |
| --- | --- | --- |
| Thêm lần xuất hiện mới của chuỗi | Có | Có nếu dòng thêm khớp regex |
| Xóa lần xuất hiện cuối cùng | Có | Có nếu dòng xóa khớp regex |
| Sửa dòng nhưng tổng số lần xuất hiện giữ nguyên | Không chỉ vì chuỗi đó | Có nếu dòng thêm/xóa khớp |
| Thay đổi một dòng có token liên quan | Chỉ khi số lần xuất hiện thay đổi | Có nếu dòng thay đổi khớp regex |
| Chỉ có chuỗi trong dòng context không đổi | Không | Không |
| Tìm theo mẫu nhiều cách viết | Dùng `--pickaxe-regex` nếu muốn regex | Regex trực tiếp |

### 4.4. Quy tắc lựa chọn nhanh

- Muốn tìm lúc một chuỗi được thêm vào hoặc biến mất: bắt đầu với `-S`.
- Muốn tìm lúc một dòng chứa token được sửa, kể cả số lần xuất hiện không đổi: dùng `-G`.
- Chưa chắc thay đổi thuộc loại nào: chạy cả hai, rồi đọc patch của các commit kết quả.

Không có bộ lọc nào tự hiểu ý nghĩa của code. Kết quả vẫn cần được đọc và xác minh theo ngữ cảnh.

## 5. Dùng chuỗi literal và biểu thức chính quy

### 5.1. -S mặc định nhận chuỗi literal

Ví dụ:

~~~bash
git log -S'config.timeout' -- config/
~~~

Ở đây dấu chấm là ký tự dấu chấm trong chuỗi tìm kiếm, không phải wildcard regex.

Nếu chuỗi có khoảng trắng hoặc ký tự shell đặc biệt, đặt trong dấu nháy:

~~~bash
git log -S'connection pool size' -- .
~~~

Dấu nháy giúp shell truyền nguyên chuỗi làm đối số cho Git.

### 5.2. Dùng --pickaxe-regex với -S

Nếu muốn `-S` đếm số lần xuất hiện của một biểu thức chính quy, thêm:

~~~bash
git log --pickaxe-regex -S'validate[A-Za-z]+' -- src/
~~~

Khi đó, đối số của `-S` được diễn giải như biểu thức chính quy mở rộng POSIX thay vì chuỗi literal.

Ví dụ này tìm thay đổi về số lần khớp của các tên bắt đầu bằng `validate` và tiếp theo là một hoặc nhiều chữ cái.

### 5.3. -G luôn nhận regex

Ví dụ:

~~~bash
git log -G'validate[A-Za-z]+' -- src/
~~~

`-G` dùng biểu thức chính quy để kiểm tra các dòng thêm/xóa. Nếu muốn tìm dấu ngoặc mở literal trong lời gọi hàm, escape nó:

~~~bash
git log -G'validate[A-Za-z]+\(' -- src/
~~~

### 5.4. Một số biểu thức hữu ích

| Mục tiêu | Regex ví dụ |
| --- | --- |
| Dòng có gọi hàm validate | `validate[A-Za-z0-9_]*\(` |
| Dòng gán biến timeout | `timeout[[:space:]]*=` |
| Dòng có TODO hoặc FIXME | `TODO|FIXME` |
| Lệnh gọi API cũ hoặc mới | `oldClient\(|newClient\(` |
| Dòng trả về false | `return[[:space:]]+false;` |
| Khóa cấu hình bắt đầu bằng feature | `feature[A-Za-z0-9_]*[[:space:]]*=` |

Các ví dụ dùng cú pháp regex mở rộng POSIX. Ký tự như ngoặc, dấu chấm, dấu cộng hoặc dấu gạch đứng có ý nghĩa đặc biệt; escape nếu muốn tìm chúng theo nghĩa literal.

### 5.5. Không dùng cú pháp regex của ngôn ngữ lập trình một cách mặc định

Regex của Git pickaxe dựa trên regex POSIX mở rộng, không phải JavaScript, Java hay PCRE trong mọi trường hợp. Ví dụ, `\s` không phải cách viết khoảng trắng di động của POSIX ERE; dùng `[[:space:]]`.

Nếu regex quá phức tạp, hãy bắt đầu bằng một mẫu đơn giản, kiểm tra kết quả, rồi tăng độ cụ thể.

## 6. Giới hạn phạm vi lịch sử tìm kiếm

### 6.1. Tìm từ HEAD theo mặc định

~~~bash
git log -S'calculateTax' -- src/
~~~

Mặc định, Git tìm trong các commit có thể truy cập từ HEAD. Nếu commit nằm trên branch khác chưa được merge vào branch hiện tại, kết quả có thể không xuất hiện.

### 6.2. Tìm trên tất cả refs bằng --all

~~~bash
git log --all --oneline -S'calculateTax' -- src/
~~~

`--all` tìm trong lịch sử có thể truy cập từ các refs được Git biết đến, như branch local, tag và remote-tracking refs đã fetch.

Nó không thể tìm commit trên remote mà repository local chưa fetch hoặc chưa có object tương ứng.

Có thể cập nhật remote-tracking refs trước:

~~~bash
git fetch --all --prune
~~~

Sau đó chạy lại tìm kiếm. `git fetch` cập nhật refs và object từ remote theo cấu hình; nó không tự merge vào branch hiện tại.

### 6.3. Giới hạn theo branch

~~~bash
git log feature/payment -S'calculateTax' -- src/
~~~

Lệnh chỉ xét lịch sử có thể truy cập từ ref `feature/payment`.

### 6.4. Tìm commit chỉ có trên một nhánh

~~~bash
git log main..feature/payment --oneline -S'calculateTax' -- src/
~~~

Khoảng `main..feature/payment` chọn commit có thể truy cập từ feature/payment nhưng không có trong main.

Điều này hữu ích khi cần tìm thay đổi trong một nhánh chưa được tích hợp.

### 6.5. Giới hạn theo khoảng thời gian

~~~bash
git log --since="2025-01-01" --until="2025-03-31" -S'calculateTax' -- src/
~~~

Kết hợp khoảng thời gian khi bạn biết thay đổi xảy ra trong một giai đoạn. Ngày tháng ở đây lọc commit theo thời gian metadata; nó không thay thế việc chọn đúng refs hoặc pathspec.

### 6.6. Sắp xếp kết quả theo thứ tự thời gian

Mặc định, git log thường hiển thị commit mới hơn trước. Muốn xem từ cũ đến mới:

~~~bash
git log --reverse --oneline -S'calculateTax' -- src/
~~~

Cách này hữu ích khi tái dựng tiến trình: chuỗi được thêm lần đầu, được thay đổi, rồi bị loại bỏ.

## 7. Giới hạn theo đường dẫn và rename

### 7.1. Dùng -- để phân cách revision và pathspec

Ví dụ:

~~~bash
git log -S'calculateTax' -- src/billing/
~~~

Phần trước `--` là revision hoặc bộ lọc; phần sau là pathspec. Dùng dấu phân cách rõ ràng để Git không nhầm tên đường dẫn với tên ref hoặc option.

Có thể tìm trong toàn repository:

~~~bash
git log -S'calculateTax' -- .
~~~

### 7.2. Tìm trong một file cụ thể

~~~bash
git log -p -S'calculateTax' -- src/billing/TaxService.java
~~~

Điều này giới hạn kết quả vào lịch sử của file hoặc đường dẫn được chọn.

### 7.3. Khi file đã đổi tên

Nếu file được rename, lịch sử theo đường dẫn mới có thể không tự bao gồm mọi commit trước rename. Dùng:

~~~bash
git log --follow -p -S'calculateTax' -- src/billing/TaxService.java
~~~

`--follow` yêu cầu Git tiếp tục theo dõi lịch sử qua rename cho một đường dẫn đơn. Tùy chọn này có giới hạn và dựa vào phát hiện rename theo nội dung; nó không giải quyết hoàn hảo mọi trường hợp copy, rename phức tạp hoặc lịch sử phân nhánh.

Nếu chưa rõ tên cũ, xem rename trong log:

~~~bash
git log --summary --find-renames -- src/billing/
~~~

### 7.4. Pathspec có thể làm bạn bỏ sót kết quả

Nếu chuỗi từng nằm trong file khác, tìm trong một file hiện tại sẽ không phát hiện các commit chỉ sửa đường dẫn cũ hoặc đường dẫn khác.

Khi chưa biết vị trí:

~~~bash
git log --all --oneline -S'calculateTax'
~~~

Sau khi tìm được commit, xem tên file bằng:

~~~bash
git show --name-status --format= <commit>
~~~

Sau đó giới hạn đường dẫn nếu cần.

## 8. Hiển thị patch của các commit tìm được

### 8.1. Thêm -p để đọc patch

~~~bash
git log -p -S'calculateTax' -- src/
~~~

`-p` hiển thị patch của từng commit phù hợp. Đây thường là cách tốt nhất để hiểu chuỗi đã được thêm, sửa hoặc xóa ra sao.

Với regex:

~~~bash
git log -p -G'calculateTax\(' -- src/
~~~

### 8.2. Dùng --oneline để lập danh sách ứng viên

~~~bash
git log --oneline -S'calculateTax' -- src/
~~~

Dạng một dòng giúp xem nhanh hash và subject. Khi đã chọn commit đáng chú ý:

~~~bash
git show <commit>
~~~

để đọc đầy đủ metadata và patch.

### 8.3. Dùng --stat để xem phạm vi commit

~~~bash
git log --stat -S'calculateTax' -- src/
~~~

Thống kê cho biết commit thay đổi những file nào và quy mô thêm/xóa. Nó giúp phân biệt một thay đổi nhỏ với một refactor lớn có cùng từ khóa.

### 8.4. Dùng --pickaxe-all để xem toàn bộ thay đổi của commit khớp

Thông thường, pickaxe có thể giới hạn phần diff được hiển thị vào các file có thay đổi khớp điều kiện. Nếu muốn khi một commit đã khớp thì xem toàn bộ thay đổi trong changeset, dùng:

~~~bash
git log -p --pickaxe-all -S'calculateTax' -- src/
~~~

Tùy chọn `--pickaxe-all` giúp đọc bối cảnh đầy đủ hơn: commit có thể thay đổi nhiều file, trong đó chỉ một phần làm điều kiện pickaxe khớp.

### 8.5. Đọc từng commit ứng viên bằng git show

Ví dụ kết quả tìm kiếm:

~~~text
a12bc34 Add tax calculation for invoices
d45ef67 Replace legacy tax helper
f89ab01 Remove obsolete tax flag
~~~

Kiểm tra commit cụ thể:

~~~bash
git show --format=fuller a12bc34
git show --format=fuller d45ef67
git show --format=fuller f89ab01
~~~

Đọc author, committer, ngày, message và patch. Đừng kết luận chỉ từ subject vì commit có thể chứa thay đổi rộng hơn tên gọi.

## 9. Phân tích các ví dụ thực tế

### 9.1. Tìm commit thêm một feature flag

Giả sử bạn muốn tìm khi nào `newCheckoutEnabled` được thêm:

~~~bash
git log --all --reverse --oneline -S'newCheckoutEnabled' -- config/
~~~

Nếu muốn xem patch:

~~~bash
git log --all -p -S'newCheckoutEnabled' -- config/
~~~

Đọc kết quả cũ nhất trước để xác định lần thêm đầu tiên. Kiểm tra file và giá trị flag tại commit đó.

### 9.2. Tìm commit loại bỏ API cũ

Giả sử API `legacyClient.request` không còn được dùng:

~~~bash
git log --all -p -G'legacyClient\.request\(' -- src/
~~~

Regex có thể tìm các dòng thêm/xóa khớp lời gọi API. Kiểm tra các commit để biết API được thay thế, di chuyển sang module khác hay chỉ đổi cách viết.

### 9.3. Tìm khi điều kiện kiểm tra quyền thay đổi

~~~bash
git log --all -p -G'hasPermission|isAuthorized' -- src/security/
~~~

Lệnh tìm commit có dòng thay đổi chứa một trong hai tên hàm. Đọc patch để xác định điều kiện đã được thêm, xóa hoặc thay đổi thứ tự đánh giá.

### 9.4. Tìm khi một giá trị mặc định thay đổi

~~~bash
git log --all -p -G'defaultTimeout[[:space:]]*=' -- config/
~~~

Regex tìm dòng gán biến cấu hình. Nếu muốn tìm chính xác số lần xuất hiện của một literal, có thể dùng:

~~~bash
git log --all -p -S'defaultTimeout = 30' -- config/
~~~

Hai cách có độ rộng khác nhau: regex có thể khớp nhiều khoảng trắng hoặc giá trị khác nhau, còn chuỗi literal chỉ khớp chính xác đoạn được chỉ định.

### 9.5. Tìm commit thêm hoặc xóa TODO

~~~bash
git log --all -p -G'TODO|FIXME' -- src/
~~~

Tìm các dòng thay đổi có chứa TODO hoặc FIXME. Nó không tìm những dòng TODO vẫn tồn tại nhưng không thay đổi trong commit.

### 9.6. Tìm thay đổi làm số lần gọi API tăng hoặc giảm

~~~bash
git log --all -p -S'httpClient.send(' -- src/
~~~

Lệnh tìm thay đổi về số lần xuất hiện của chuỗi gọi API. Nếu cách gọi được viết lại nhưng số lần xuất hiện giữ nguyên, dùng `-G` để tìm dòng thay đổi:

~~~bash
git log --all -p -G'httpClient\.send\(' -- src/
~~~

## 10. Kết hợp pickaxe với các bộ lọc khác

### 10.1. Kết hợp tác giả

~~~bash
git log --all --author='Nguyen Van An' -S'calculateTax' -- src/
~~~

Dùng khi bạn muốn thu hẹp kết quả theo người được ghi nhận là author. Lưu ý author metadata không tự chứng minh danh tính thật; đây chỉ là bộ lọc trên dữ liệu commit.

### 10.2. Kết hợp commit message

~~~bash
git log --all --grep='tax' -S'calculateTax' -- src/
~~~

`--grep` lọc commit message, còn `-S` lọc thay đổi nội dung. Chỉ các commit thỏa mãn cả hai điều kiện mới xuất hiện.

Nếu muốn regex cho message, Git có các tùy chọn riêng như `--extended-regexp`; đừng nhầm chúng với `--pickaxe-regex`, vốn điều khiển cách diễn giải chuỗi của `-S`.

### 10.3. Kết hợp thời gian và nhánh

~~~bash
git log feature/payment --since="2025-01-01" -G'paymentStatus' -- src/
~~~

Kết quả chỉ xét lịch sử từ branch đã chỉ định, trong khoảng thời gian đã chọn và các dòng thay đổi khớp regex.

### 10.4. Kết hợp giới hạn kết quả

~~~bash
git log --all --oneline -S'calculateTax' -n 20 -- src/
~~~

`-n 20` giới hạn số commit hiển thị. Nếu kết quả quá nhiều, bắt đầu bằng danh sách ngắn rồi bỏ giới hạn khi cần tìm lịch sử sâu hơn.

## 11. Các trường hợp đặc biệt cần chú ý

### 11.1. Merge commit

Mặc định, Git không hiển thị diff thông thường cho merge commit trong nhiều chế độ log. Nếu thay đổi bạn tìm được đưa vào thông qua merge, kết quả pickaxe có thể không cho thấy merge commit theo cách bạn mong đợi.

Thử yêu cầu diff riêng với từng parent:

~~~bash
git log --all -m -p -S'calculateTax' -- src/
~~~

Hoặc với regex:

~~~bash
git log --all -m -p -G'calculateTax' -- src/
~~~

Sau khi tìm thấy merge commit, xem các phía:

~~~bash
git show -m <merge-commit>
git show --cc <merge-commit>
~~~

Dùng `-m` để xem diff riêng với từng parent; `--cc` để xem combined diff. Không nên suy luận nội dung merge chỉ từ một danh sách commit ngắn.

### 11.2. Commit gốc

Commit đầu tiên không có parent. Khi một file hoặc chuỗi được thêm lần đầu trong commit gốc, Git có thể so sánh nội dung với cây rỗng.

Tìm kiếm:

~~~bash
git log --reverse -S'initialSetting' -- .
~~~

Nếu kết quả là commit gốc, không thể dùng `<commit>^` để đọc phiên bản trước đó vì không có parent. Hãy xem nội dung trực tiếp:

~~~bash
git show <root-commit>:config/app.yml
~~~

### 11.3. File nhị phân

`-G` tìm dòng thêm/xóa khớp regex nên không phù hợp với nội dung nhị phân không có dòng văn bản thông thường. `-S` cũng không nên được coi là công cụ tìm nội dung đáng tin cho mọi định dạng binary.

Nếu cần điều tra file nhị phân, xác định commit thay đổi đường dẫn:

~~~bash
git log --all --name-status -- path/to/asset.bin
~~~

Sau đó so sánh OID, trích xuất phiên bản và dùng công cụ chuyên biệt để kiểm tra nội dung.

### 11.4. Submodule

Repository cha lưu submodule dưới dạng gitlink trỏ đến commit của repository con. Pickaxe trên repository cha không tìm sâu vào source code của repository con.

Nếu chuỗi nằm trong submodule, chuyển vào repository con và chạy `git log -S` hoặc `-G` tại đó.

### 11.5. Git LFS

Trong repository dùng Git LFS, Git thường lưu pointer text thay vì nội dung file lớn. Pickaxe trong repository chính có thể chỉ xét pointer hoặc metadata được commit, không phải nội dung binary bên ngoài.

Muốn tìm thay đổi trong nội dung LFS, cần lấy các LFS object và dùng công cụ phù hợp với định dạng. Không giả định `git log -S` đã tìm bên trong ảnh, video hoặc model.

### 11.6. Rename và copy

Git suy luận rename/copy khi so sánh tree. Với đường dẫn đổi tên, pathspec chỉ tên mới có thể không bao phủ lịch sử tên cũ. Dùng `--follow` với một file và kiểm tra `--summary --find-renames` để hiểu kết quả.

Việc phát hiện rename dựa trên độ tương đồng nội dung và có thể không nhận diện đúng mọi trường hợp.

### 11.7. Kết quả rỗng không chứng minh chuỗi chưa từng tồn tại

Không có kết quả có thể do:

- Tìm từ HEAD nhưng commit nằm trên branch khác.
- Remote chưa fetch.
- Pathspec giới hạn sai thư mục hoặc tên file.
- Chuỗi được thay đổi nhưng số lần xuất hiện không đổi nên `-S` không khớp.
- Regex không đúng cú pháp POSIX ERE.
- Thay đổi nằm trong merge commit, binary hoặc submodule.
- File đã rename và lịch sử cũ nằm dưới đường dẫn khác.

Khi kết quả rỗng, mở rộng phạm vi theo từng bước thay vì kết luận ngay.

## 12. Quy trình điều tra từ chuỗi đến commit

Giả sử bạn thấy hàm `authorizePayment` trong code và muốn tìm commit đã thay đổi cách sử dụng hàm.

### Bước 1 — Tìm trong working tree hiện tại

~~~bash
git grep 'authorizePayment'
~~~

Xác định file và đường dẫn đang có chuỗi.

### Bước 2 — Tìm commit thay đổi số lần xuất hiện

~~~bash
git log --all --oneline -S'authorizePayment' -- src/
~~~

Nếu muốn xem toàn bộ patch:

~~~bash
git log --all -p -S'authorizePayment' -- src/
~~~

### Bước 3 — Tìm cả những lần sửa dòng nhưng số lượng không đổi

~~~bash
git log --all --oneline -G'authorizePayment\(' -- src/
~~~

So sánh kết quả với `-S`. Các commit chỉ xuất hiện trong kết quả `-G` có thể là những lần đổi cách gọi hoặc sắp xếp lại logic mà số lượng lời gọi không thay đổi.

### Bước 4 — Mở commit đáng chú ý

~~~bash
git show --format=fuller <commit>
~~~

Đọc author, committer, thời gian, message và patch.

### Bước 5 — Xác minh phiên bản trước và sau

Giả sử commit thay đổi file `src/payment/PaymentService.java`:

~~~bash
git show <commit>^:src/payment/PaymentService.java
git show <commit>:src/payment/PaymentService.java
~~~

Lệnh đầu đọc nội dung ở parent; lệnh sau đọc nội dung sau commit. Nếu commit là root hoặc file chưa tồn tại ở parent, lệnh đầu có thể không có kết quả.

### Bước 6 — Theo dõi các thay đổi tiếp theo

~~~bash
git log --oneline <commit>..HEAD -- src/payment/PaymentService.java
~~~

Xem các commit sau commit đã tìm được trên nhánh hiện tại. Nếu cần hiểu dòng hiện tại được sửa lần cuối bởi ai, dùng:

~~~bash
git blame src/payment/PaymentService.java
~~~

`git blame` trả lời câu hỏi về nguồn gốc các dòng hiện tại; pickaxe trả lời câu hỏi về các commit có thay đổi khớp nội dung.

### Bước 7 — Ghi lại kết luận có căn cứ

Khi báo cáo nguyên nhân, lưu:

- Commit hash đầy đủ.
- Branch/ref và phạm vi lịch sử đã tìm.
- Đường dẫn file.
- Patch chứng minh thay đổi.
- Phiên bản trước và sau nếu cần.
- Các giới hạn đã kiểm tra như rename, merge hoặc submodule.

Không kết luận rằng một commit là nguyên nhân chỉ vì nó chứa từ khóa. Đọc patch và kiểm tra hành vi trong ngữ cảnh.

## 13. Những sai lầm thường gặp

- **Nghĩ -S và -G giống nhau:** `-S` so sánh số lần xuất hiện; `-G` khớp các dòng được thêm/xóa.
- **Dùng -S khi số lượng chuỗi không thay đổi:** commit có thể không xuất hiện. Thử `-G`.
- **Dùng -G như tìm chuỗi trong toàn bộ file:** nó xét dòng thêm/xóa, không phải mọi dòng context hoặc toàn bộ working tree.
- **Quên -- trước pathspec:** Git có thể diễn giải sai đối số. Phân cách revision và đường dẫn rõ ràng.
- **Chỉ tìm từ HEAD:** commit ở branch khác có thể bị bỏ qua. Dùng `--all` khi cần mở rộng phạm vi.
- **Quên fetch remote:** `--all` chỉ tìm refs và object local đã biết; fetch để cập nhật remote-tracking refs.
- **Nhầm -S với regex:** mặc định -S là chuỗi literal; thêm `--pickaxe-regex` nếu muốn regex.
- **Dùng regex của ngôn ngữ khác:** pickaxe dùng regex POSIX mở rộng; kiểm tra cách escape.
- **Chỉ đọc subject:** commit message không chứng minh nội dung. Dùng `-p` hoặc `git show`.
- **Bỏ qua merge commit:** nếu nghi thay đổi đến từ merge, thử `-m` và xem từng parent.
- **Tìm binary/submodule như source bình thường:** pickaxe không tự đi sâu vào object ngoài hoặc repository con.
- **Coi kết quả rỗng là bằng chứng tuyệt đối:** kiểm tra refs, pathspec, rename, số lần xuất hiện và regex trước.

## 14. Bảng tra cứu nhanh

| Nhu cầu | Lệnh |
| --- | --- |
| Tìm commit làm thay đổi số lần xuất hiện literal | `git log -S'featureFlag' -- .` |
| Tìm commit có dòng thay đổi khớp regex | `git log -G'featureFlag[[:space:]]*=' -- .` |
| Xem patch của commit khớp -S | `git log -p -S'calculateTax' -- src/` |
| Xem patch của commit khớp -G | `git log -p -G'calculateTax\(' -- src/` |
| Tìm trên mọi ref local đã biết | `git log --all -S'calculateTax' -- .` |
| Xem commit dạng một dòng | `git log --oneline -S'calculateTax' -- src/` |
| Tìm theo regex với -S | `git log --pickaxe-regex -S'validate[A-Za-z]+' -- src/` |
| Hiển thị toàn bộ thay đổi của commit khớp | `git log -p --pickaxe-all -S'calculateTax' -- src/` |
| Tìm trong branch cụ thể | `git log feature/payment -S'calculateTax' -- src/` |
| Tìm commit riêng của branch | `git log main..feature/payment -S'calculateTax' -- src/` |
| Theo dõi file qua rename | `git log --follow -p -S'calculateTax' -- src/TaxService.java` |
| Tìm trong merge commit theo từng parent | `git log -m -p -S'calculateTax' -- src/` |
| Xem commit đã tìm | `git show --format=fuller <commit>` |
| Xem nội dung file sau commit | `git show <commit>:path/to/file` |
| Xem nội dung file ở parent | `git show <commit>^:path/to/file` |
| Tìm chuỗi trong working tree hiện tại | `git grep 'calculateTax'` |
| Xem nguồn gốc dòng hiện tại | `git blame path/to/file` |

## 15. Tổng kết

`git log -S` và `git log -G` giúp tìm commit theo nội dung diff. `-S` chọn commit làm thay đổi số lần xuất hiện của một chuỗi; `-G` chọn commit có dòng được thêm hoặc xóa khớp regex. Nếu thay đổi làm số lượng token giữ nguyên nhưng dòng code thay đổi, `-G` thường phù hợp hơn. Nếu muốn biết khi nào một chuỗi được thêm hoặc biến mất, bắt đầu với `-S`.

Kết hợp pickaxe với `-p`, `--all`, pathspec và các revision range để thu hẹp lịch sử, sau đó dùng `git show` để đọc commit và xác minh phiên bản trước/sau. Khi gặp kết quả rỗng, kiểm tra phạm vi refs, rename, merge, regex và giới hạn của binary, submodule hoặc Git LFS.

Điều quan trọng là dùng pickaxe để tìm ứng viên, rồi đọc patch và xác minh hành vi. Cách làm này giúp truy tìm thời điểm một đoạn code được thêm, sửa hoặc xóa mà không phải duyệt thủ công toàn bộ lịch sử.

