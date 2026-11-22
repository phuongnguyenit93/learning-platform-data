# Đọc bản vá: đường dẫn, vùng thay đổi và dòng thêm hoặc xóa

Khi xem thay đổi bằng Git, bạn thường gặp một bản vá (patch) ở dạng **unified diff**. Bản vá mô tả tệp nào thay đổi, vị trí thay đổi và những dòng được giữ lại, thêm vào hoặc xóa đi. Đọc được cấu trúc này giúp bạn review code, kiểm tra nội dung sắp commit, hiểu kết quả merge và tìm chính xác phần thay đổi mà không phải đọc lại toàn bộ tệp.

Trong phạm vi quản lý mã nguồn bằng Git, bản vá là cách trình bày sự khác biệt giữa hai trạng thái của repository. Một bản vá không nhất thiết là toàn bộ nội dung tệp; nó thường chỉ chứa các vùng quanh dòng thay đổi, kèm một số dòng ngữ cảnh để người đọc định vị.

## 1. Bản vá unified diff gồm những phần nào?

Một diff thông thường có thể gồm:

1. **File header:** cho biết đường dẫn tệp ở phía cũ và phía mới.
2. **Metadata:** OID, file mode, trạng thái tạo/xóa/đổi tên hoặc thông tin bổ sung.
3. **Hunk header:** cho biết vùng dòng nào của bản cũ và bản mới đang được trình bày.
4. **Hunk body:** các dòng ngữ cảnh, dòng bị xóa và dòng được thêm.

Ví dụ rút gọn:

~~~diff
diff --git a/src/greeting.js b/src/greeting.js
index 12ab34c..56de78f 100644
--- a/src/greeting.js
+++ b/src/greeting.js
@@ -10,4 +10,5 @@ function greet(name) {
   const normalized = name.trim();
-  return "Hello " + normalized;
+  const message = "Hello " + normalized;
+  return message;
 }
 
~~~

Đọc từ trên xuống:

- Tệp được so sánh là src/greeting.js.
- Dòng index cho biết OID rút gọn của nội dung cũ và mới; 100644 là file mode.
- --- là phía cũ, +++ là phía mới.
- Hunk bắt đầu ở vùng dòng 10 của cả hai phiên bản.
- Dòng bắt đầu bằng dấu cách là ngữ cảnh; dấu - biểu thị dòng bị xóa; dấu + biểu thị dòng được thêm.

## 2. Đọc file header và đường dẫn a/, b/

Dòng đầu của mỗi tệp thường có dạng:

~~~diff
diff --git a/src/greeting.js b/src/greeting.js
~~~

Trong quy ước unified diff của Git:

- a/ là tiền tố cho đường dẫn ở phía cũ.
- b/ là tiền tố cho đường dẫn ở phía mới.
- Phần sau tiền tố là đường dẫn tương ứng trong cây tệp.

Hai đường dẫn giống nhau thường biểu thị cùng một tệp được sửa nội dung. Nếu đường dẫn khác nhau, diff có thể đang biểu diễn đổi tên hoặc di chuyển tệp, tùy metadata đi kèm.

Các dòng tiếp theo thường là:

~~~diff
--- a/src/greeting.js
+++ b/src/greeting.js
~~~

--- và +++ xác định tên tệp ở hai phía trong định dạng patch. Khi thêm tệp mới, phía cũ thường là /dev/null; khi xóa tệp, phía mới thường là /dev/null:

~~~diff
diff --git a/docs/new-guide.md b/docs/new-guide.md
new file mode 100644
--- /dev/null
+++ b/docs/new-guide.md
@@ -0,0 +1,2 @@
+# New guide
+Installation steps
~~~

Ví dụ xóa tệp:

~~~diff
diff --git a/docs/old-guide.md b/docs/old-guide.md
deleted file mode 100644
--- a/docs/old-guide.md
+++ /dev/null
@@ -1,2 +0,0 @@
-# Old guide
-Deprecated instructions
~~~

Tiền tố a/ và b/ là cách đặt tên trong bản diff, không có nghĩa repository của bạn phải chứa hai thư mục thật tên là a và b.

## 3. Metadata trong diff

Trước phần nội dung, Git có thể hiển thị metadata mô tả object và trạng thái tệp:

~~~diff
index 12ab34c..56de78f 100644
~~~

- 12ab34c là OID rút gọn của blob cũ.
- 56de78f là OID rút gọn của blob mới.
- 100644 là mode của tệp thông thường không có quyền thực thi trên hệ thống kiểu Unix.

Một số file mode thường gặp:

| Mode | Ý nghĩa |
|---|---|
| 100644 | Tệp thông thường, không executable |
| 100755 | Tệp thông thường, executable |
| 120000 | Symbolic link |
| 160000 | Gitlink, thường dùng cho submodule |

Khi thay đổi quyền thực thi, Git có thể hiển thị:

~~~diff
old mode 100644
new mode 100755
~~~

Khi tạo hoặc xóa tệp, metadata có thể gồm new file mode hoặc deleted file mode. Những thay đổi này quan trọng vì diff không chỉ mô tả nội dung văn bản; nó còn có thể ghi nhận thay đổi metadata mà Git quản lý.

## 4. Đọc hunk header @@

Một hunk header trong unified diff có dạng:

~~~text
@@ -<old-start>,<old-count> +<new-start>,<new-count> @@ <context>
~~~

Ví dụ:

~~~diff
@@ -10,4 +10,5 @@ function greet(name) {
~~~

Ý nghĩa:

- -10,4: vùng được hiển thị bắt đầu tại dòng 10 của phiên bản cũ và gồm 4 dòng.
- +10,5: vùng tương ứng bắt đầu tại dòng 10 của phiên bản mới và gồm 5 dòng.
- function greet(name) {: phần context tùy chọn, giúp nhận biết hàm hoặc khu vực đang được sửa.

Số dòng bên trái dấu - luôn tham chiếu phiên bản cũ; số dòng bên phải dấu + tham chiếu phiên bản mới. Hai số đếm có thể khác nhau vì hunk có thể thêm hoặc xóa dòng.

### Khi số lượng dòng bị lược bỏ

Nếu vùng chỉ có một dòng, định dạng diff có thể bỏ phần ,count:

~~~diff
@@ -8 +8 @@
~~~

Điều này tương đương với một dòng ở phiên bản cũ và một dòng ở phiên bản mới. Nếu số lượng là 0, Git ghi rõ ,0, ví dụ:

~~~diff
@@ -0,0 +1,2 @@
~~~

Đây là trường hợp thêm hai dòng vào đầu tệp: phía cũ không có dòng nào trong vùng đó, phía mới có hai dòng bắt đầu tại dòng 1.

### Hunk context không phải dòng thay đổi

Phần chữ sau @@ thứ hai thường là ngữ cảnh do Git chọn, chẳng hạn tên hàm hoặc cấu trúc gần vùng thay đổi. Nó không phải một dòng mới trong file patch body và không làm tăng số dòng được tính trong hunk.

## 5. Phân biệt dòng ngữ cảnh, thêm và xóa

Trong phần thân hunk, ký tự đầu tiên của mỗi dòng cho biết cách đọc:

| Ký tự đầu dòng | Ý nghĩa | Có trong phiên bản cũ? | Có trong phiên bản mới? |
|---|---|---:|---:|
| Dấu cách | Dòng ngữ cảnh, không thay đổi | Có | Có |
| - | Dòng bị xóa | Có | Không |
| + | Dòng được thêm | Không | Có |

Ví dụ:

~~~diff
@@ -20,3 +20,4 @@
 const enabled = true;
-const timeout = 1000;
+const timeout = 2500;
+const retries = 3;
 startService();
~~~

Diễn giải:

- const enabled = true; và startService(); là dòng ngữ cảnh.
- const timeout = 1000; tồn tại ở phiên bản cũ và bị loại khỏi phiên bản mới.
- const timeout = 2500; được thêm vào phiên bản mới để thay giá trị cũ.
- const retries = 3; là dòng mới được bổ sung.

Một cặp dòng - và + liền nhau thường là một dòng được thay thế. Tuy nhiên, Git chỉ biểu diễn sự khác biệt theo nội dung; việc hai dòng có cùng ý nghĩa hay không vẫn cần người review hiểu mã nguồn để đánh giá.

## 6. Tự tính số dòng của một hunk

Hunk header cho biết số dòng của hai phía. Có thể kiểm tra bằng cách đếm ký hiệu trong hunk body:

- Dòng bắt đầu bằng dấu cách được tính cho cả cũ và mới.
- Dòng bắt đầu bằng - chỉ được tính cho cũ.
- Dòng bắt đầu bằng + chỉ được tính cho mới.
- Dòng metadata như \ No newline at end of file không được tính là một dòng nội dung của hunk.

Với ví dụ ở phần trước:

~~~diff
@@ -20,3 +20,4 @@
 const enabled = true;
-const timeout = 1000;
+const timeout = 2500;
+const retries = 3;
 startService();
~~~

Phía cũ có 3 dòng: hai dòng ngữ cảnh và một dòng xóa. Phía mới có 4 dòng: hai dòng ngữ cảnh và hai dòng thêm. Vì vậy header -20,3 +20,4 khớp với nội dung hunk.

Khi review patch thật, nếu số dòng bạn đếm không khớp hunk header, hãy kiểm tra xem bạn có bỏ sót dòng context, dòng thêm/xóa hoặc marker cuối tệp hay không.

## 7. Một tệp có thể có nhiều hunk

Git thường gom các thay đổi gần nhau thành một hunk. Nếu hai vùng sửa cách xa nhau, diff có thể hiển thị nhiều hunk riêng:

~~~diff
diff --git a/src/config.js b/src/config.js
--- a/src/config.js
+++ b/src/config.js
@@ -4,3 +4,3 @@
-const host = "localhost";
+const host = "127.0.0.1";
 const port = 8080;
 const secure = false;
@@ -40,3 +40,4 @@
 function connect() {
+  validateConfig();
   return openConnection();
 }
~~~

Mỗi hunk có cặp vị trí và số dòng riêng. Hunk thứ hai không tiếp tục đếm từ số dòng của hunk thứ nhất; nó chỉ ra vùng khác trong cùng tệp.

Mặc định Git thường đưa một số dòng ngữ cảnh xung quanh thay đổi để người đọc hiểu vị trí. Có thể tăng hoặc giảm số dòng context bằng tùy chọn -U:

~~~bash
# Không hiển thị dòng context
git diff -U0

# Hiển thị 5 dòng context quanh mỗi thay đổi
git diff -U5
~~~

Ít context làm patch ngắn hơn nhưng khó định vị hơn. Nhiều context giúp review dễ hơn, đổi lại output dài hơn.

## 8. Marker cuối tệp: No newline at end of file

Một dòng đặc biệt có thể xuất hiện sau hunk:

~~~text
\ No newline at end of file
~~~

Đây là thông báo rằng phiên bản tương ứng không kết thúc bằng ký tự xuống dòng. Dòng này không phải nội dung thực của tệp và không được tính vào số dòng hunk. Tệp văn bản thường nên kết thúc bằng newline để công cụ Unix, diff và một số trình xử lý văn bản hoạt động nhất quán.

Nếu cả phiên bản cũ và mới đều không có newline, marker có thể xuất hiện ở cả hai phía. Nếu chỉ một phía thiếu newline, marker xuất hiện cạnh dòng thuộc phía đó.

## 9. Đọc thay đổi thêm, xóa, đổi tên và đổi mode

### Tệp mới

Tệp mới thường có new file mode, phía cũ là /dev/null, và hunk bắt đầu với vị trí cũ -0,0.

### Tệp bị xóa

Tệp bị xóa thường có deleted file mode, phía mới là /dev/null, và phần hunk chỉ có dòng -.

### Đổi tên hoặc di chuyển

Git có thể nhận diện rename dựa trên mức độ tương đồng giữa nội dung cũ và mới. Ví dụ:

~~~diff
diff --git a/src/old-name.js b/src/new-name.js
similarity index 92%
rename from src/old-name.js
rename to src/new-name.js
~~~

similarity index là mức tương đồng Git ước lượng giữa hai phiên bản. Nếu chỉ đổi tên mà không sửa nội dung, mức tương đồng có thể là 100%. Nếu vừa đổi tên vừa sửa nội dung, phần patch nội dung có thể xuất hiện sau metadata rename.

Git không lưu một loại object riêng cho thao tác rename. Rename được suy luận khi so sánh hai cây tệp dựa trên nội dung và ngưỡng nhận diện.

### Thay đổi quyền thực thi

~~~diff
old mode 100644
new mode 100755
~~~

Đây là thay đổi file mode, không nhất thiết có thay đổi nội dung. Trên một số hệ thống tệp hoặc cấu hình, Git có thể không nhận diện mọi khác biệt permission; cấu hình core.fileMode ảnh hưởng việc kiểm tra mode của working tree.

## 10. Diff của tệp nhị phân và submodule

Tệp nhị phân như ảnh, PDF, archive hoặc executable không thể trình bày an toàn bằng các dòng văn bản thông thường. Git có thể hiển thị:

~~~text
Binary files a/assets/logo.png and b/assets/logo.png differ
~~~

Để tạo patch nhị phân có thể dùng --binary:

~~~bash
git diff --binary > changes.patch
~~~

Patch này có thể chứa dữ liệu nhị phân được mã hóa để áp dụng thay đổi. Không nên đọc phần dữ liệu đó như văn bản nguồn; dùng công cụ phù hợp để so sánh hoặc xem trước file.

Với submodule, diff ở kho cha thường mô tả gitlink thay đổi từ OID commit này sang OID commit khác. Có thể yêu cầu hiển thị commit log:

~~~bash
git diff --submodule=log
~~~

Điều này giúp reviewer biết submodule đã tiến từ commit nào đến commit nào. Nội dung các tệp bên trong repository con vẫn thuộc lịch sử của chính submodule.

## 11. Đọc diff trong các ngữ cảnh Git khác nhau

Cùng định dạng patch có thể được tạo khi so sánh các cặp trạng thái khác nhau. Cần biết rõ hai phía đang được so sánh:

| Lệnh | So sánh | Câu hỏi được trả lời |
|---|---|---|
| git diff | Working tree với index | Những gì tôi sửa nhưng chưa stage? |
| git diff --cached | Index với HEAD | Những gì sẽ được đưa vào commit tiếp theo? |
| git diff HEAD | Working tree và index với commit hiện tại | Tổng thay đổi chưa commit là gì? |
| git diff <commit-A> <commit-B> | Hai commit | Hai trạng thái lịch sử khác nhau ở đâu? |
| git show <commit> | Commit với parent, kèm metadata | Commit này đã thay đổi gì? |
| git diff <branch-A>...<branch-B> | Merge base của A với B | Nhánh B đã thay đổi gì kể từ điểm chung với A? |

Ví dụ review phần chuẩn bị commit:

~~~bash
git status --short
git diff
git diff --cached
git diff --check
git diff --cached --check
~~~

Không nên chỉ nhìn một lệnh git diff rồi kết luận commit sẽ chứa nội dung đó. Nếu có thay đổi staged và unstaged cùng lúc, cần xem cả hai vùng.

## 12. Tùy chọn hữu ích khi đọc bản vá

Một số tùy chọn giúp bản diff dễ đọc hơn:

| Tùy chọn | Công dụng |
|---|---|
| --stat | Tóm tắt số tệp và số dòng thêm/xóa |
| --numstat | Xuất số dòng thêm/xóa theo dạng phù hợp cho script |
| --name-only | Chỉ liệt kê tên tệp thay đổi |
| --name-status | Liệt kê tên tệp cùng trạng thái A/M/D/R/C |
| --summary | Hiển thị metadata như tạo/xóa tệp, mode, rename |
| -U<n> | Điều chỉnh số dòng context |
| --word-diff | So sánh theo từ thay vì chỉ theo dòng |
| --color-words | Tô màu phần thay đổi theo từ |
| --ignore-space-change | Bỏ qua một số khác biệt về lượng whitespace |
| --ignore-all-space | Bỏ qua khác biệt whitespace khi so sánh |
| --find-renames | Bật nhận diện rename |
| --no-prefix | Bỏ tiền tố a/ và b/ |
| --src-prefix, --dst-prefix | Đổi tiền tố đường dẫn trong output |

Ví dụ:

~~~bash
git diff --stat
git diff --name-status
git diff --summary
git diff --word-diff
git diff -U8
~~~

Các tùy chọn bỏ qua whitespace có thể hữu ích khi review thay đổi định dạng lớn, nhưng chúng cũng có thể che mất khác biệt có ý nghĩa trong ngôn ngữ hoặc file cấu hình. Hãy kiểm tra lại diff đầy đủ trước khi chấp nhận patch.

## 13. Combined diff khi xem merge commit

Merge commit có nhiều parent. Khi xem diff của merge commit, Git có thể dùng combined diff với header dạng @@@ thay vì @@:

~~~text
diff --cc src/config.js
index <parent-1-oid>,<parent-2-oid>..<result-oid>
--- a/src/config.js
+++ b/src/config.js
@@@ -10,3 -10,3 +10,4 @@@
~~~

Combined diff đặt nhiều cột để thể hiện nội dung so với nhiều parent. Cách đọc phức tạp hơn unified diff hai phía thông thường. Nếu muốn so sánh merge result với từng parent riêng, dùng:

~~~bash
git diff HEAD^1 HEAD
git diff HEAD^2 HEAD
~~~

Hai lệnh tạo diff hai phía quen thuộc, giúp review phần kết quả merge so với từng nhánh cha.

## 14. Quy trình đọc một patch khi review

Khi nhận patch từ đồng đội hoặc xem output của git diff, hãy đọc theo thứ tự:

1. **Xác định phạm vi:** xem file header và danh sách tệp để biết thay đổi ảnh hưởng khu vực nào.
2. **Kiểm tra metadata:** tìm tệp mới/xóa, rename, mode change, symlink, submodule hoặc binary.
3. **Đọc hunk header:** xác định vùng dòng cũ và mới; chú ý hunk có nhiều đoạn trong cùng tệp.
4. **Đọc dòng thêm/xóa:** so sánh logic cũ và mới; dòng context giúp hiểu khu vực xung quanh.
5. **Kiểm tra whitespace và newline:** để ý marker cuối tệp và các thay đổi định dạng.
6. **Đối chiếu đúng trạng thái:** xác nhận patch đang so sánh working tree, index hay hai commit.
7. **Kiểm tra ngữ cảnh rộng hơn:** nếu thay đổi logic, đọc thêm code gọi, test và cấu hình liên quan.

Một bản vá ngắn vẫn có thể gây thay đổi hành vi lớn. Số dòng thêm/xóa chỉ là số liệu về văn bản, không phải thước đo độ rủi ro hoặc chất lượng.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Dòng + là dòng ở phiên bản cũ | Không. + là dòng có trong phiên bản mới; - là dòng có trong phiên bản cũ. |
| Dòng có dấu cách đầu tiên là thay đổi | Không. Dấu cách biểu thị dòng context xuất hiện ở cả hai phía. |
| @@ -10,4 +10,5 @@ nói rằng thay đổi bắt đầu ở dòng 10 và thêm 5 dòng | Nó mô tả vùng cũ 4 dòng và vùng mới 5 dòng; không có nghĩa cả 5 dòng đều được thêm. |
| a/ và b/ là thư mục thật trong project | Không. Đây là tiền tố đường dẫn theo quy ước diff của Git. |
| Hunk header chỉ ra dòng thay đổi đầu tiên | Nó chỉ ra điểm bắt đầu của vùng hunk; hunk còn chứa các dòng context. |
| Rename là một loại object riêng trong Git | Không. Git suy luận rename khi so sánh các cây tệp. |
| Mọi diff đều là văn bản có thể đọc | Không. Binary diff có thể chỉ báo hai file khác nhau hoặc chứa dữ liệu mã hóa khi dùng --binary. |
| git diff luôn hiển thị thứ sẽ được commit | Không. git diff so sánh working tree với index; dùng git diff --cached để xem nội dung staged. |
| Combined diff của merge commit giống hunk hai phía | Không. Combined diff có thể dùng @@@ và biểu diễn nhiều parent. |

## 16. Tự kiểm tra

1. **Trong unified diff, dấu + và - biểu thị điều gì?**
   - + là dòng được thêm vào phiên bản mới; - là dòng bị xóa khỏi phiên bản cũ.
2. **Dòng bắt đầu bằng một dấu cách trong hunk có nghĩa gì?**
   - Đó là dòng context, có ở cả phiên bản cũ và mới.
3. **@@ -12,4 +12,6 @@ cho biết điều gì?**
   - Hunk bắt đầu ở dòng 12 phía cũ với 4 dòng và dòng 12 phía mới với 6 dòng.
4. **Vì sao một hunk có thể có số dòng cũ và mới khác nhau?**
   - Vì có dòng được thêm hoặc xóa trong vùng đó.
5. **/dev/null xuất hiện trong file header khi nào?**
   - Khi phía cũ không có tệp (tạo mới) hoặc phía mới không có tệp (xóa tệp).
6. **Lệnh nào xem thay đổi đã stage?**
   - git diff --cached hoặc git diff --staged.
7. **Git nhận diện rename bằng cách nào?**
   - Bằng cách so sánh nội dung và ước lượng mức độ tương đồng giữa đường dẫn cũ và mới.
8. **Marker \ No newline at end of file có được tính vào số dòng hunk không?**
   - Không. Đây là metadata cho biết tệp thiếu newline cuối dòng.

## Kết luận

Unified diff cho biết đường dẫn ở hai phía, metadata của tệp, vùng dòng được so sánh và nội dung thêm/xóa/ngữ cảnh. Hãy đọc file header trước, sau đó đọc hunk header @@ để xác định số dòng cũ/mới, rồi phân biệt dấu cách, - và + trong phần thân. Kiểm tra thêm metadata rename/mode, binary và trạng thái đang so sánh để hiểu đúng phạm vi bản vá. Khi review, kết hợp git diff, git diff --cached, git diff --stat và các tùy chọn context phù hợp để xác định chính xác nội dung sẽ được commit.
