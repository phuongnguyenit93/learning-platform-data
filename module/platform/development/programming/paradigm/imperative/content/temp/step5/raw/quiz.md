Câu 1. Điểm đặc trưng của lập trình mệnh lệnh là gì?
A. Chỉ mô tả ràng buộc kết quả để engine giải
B. Chuỗi lệnh điều khiển và thay đổi trạng thái
C. Chỉ mô tả quan hệ logic mà không gán biến
D. Chỉ mô tả luồng dữ liệu không có lệnh điều khiển
Đáp án đúng: B

Câu 2. Với `int x = 2; x += 3; x *= 2;`, giá trị cuối của `x` là gì?
A. Giá trị `10` sau khi cộng `3` rồi nhân `2`
B. Giá trị `8` vì cộng trước rồi nhân giá trị cũ
C. Giá trị `12` vì cả hai phép tính dùng giá trị mới
D. Giá trị `7` vì phép nhân diễn ra trước phép cộng
Đáp án đúng: A

Câu 3. Câu lệnh `x = x + 1` đối với biến số nguyên mutable có tác dụng gì?
A. Đọc giá trị x rồi ghi x tăng thêm một đơn vị
B. Lưu công thức vào x mà chưa tính toán kết quả
C. So sánh x và x cộng một, không thay đổi biến
D. Tạo một biến x khác tại mỗi lần chạy lệnh
Đáp án đúng: A

Câu 4. Hai lần gọi thủ tục tăng cùng một biến đếm toàn cục có điểm gì đáng lưu ý?
A. Mỗi lần gọi tạo biến toàn cục riêng biệt mới
B. Lần sau thấy biến đếm đã tăng từ lần trước
C. Thứ tự lời gọi không ảnh hưởng trạng thái chung
D. Mọi lần gọi đều thấy biến đếm mang giá trị gốc
Đáp án đúng: B

Câu 5. Với Java `List a = new ArrayList(); List b = a; b.add(1);`, điều gì đúng?
A. Cả `a` và `b` cùng tham chiếu list có một phần tử
B. `b` thêm vào list khác do Java sao chép tham chiếu
C. `a` vẫn rỗng vì phép gán sao chép toàn bộ list
D. `a` trỏ sang list mới khi `b` gọi `add(1)`
Đáp án đúng: A

Câu 6. Trong Java, truyền một tham chiếu đối tượng vào method tuân theo cơ chế nào?
A. Giá trị tham chiếu được sao chép vào tham số
B. Toàn bộ object được sao chép vào tham số method
C. Biến tham chiếu của caller được truyền trực tiếp
D. Method luôn nhận một con trỏ không thể gán lại
Đáp án đúng: A

Câu 7. Nếu method Java gán tham số `list = new ArrayList<>()`, ảnh hưởng tới caller là gì?
A. Các phần tử list cũ tự động bị xóa sạch
B. Tham chiếu list của caller luôn trỏ list mới
C. Tham chiếu list của caller không bị gán lại
D. Biến caller được thay bằng `null` khi return
Đáp án đúng: C

Câu 8. Đoạn Java `int n; System.out.println(n);` trong method gây điều gì?
A. In giá trị `0` vì Java tự khởi tạo local int
B. In giá trị `null` vì biến cục bộ mặc định rỗng
C. Lỗi biên dịch vì biến cục bộ chưa được gán
D. In một số bất kỳ từ ô nhớ của biến cục bộ
Đáp án đúng: C

Câu 9. Biến cục bộ khai báo bên trong cặp `{}` chỉ dùng được ở đâu?
A. Trong mọi method khác cùng một lớp chứa khối
B. Trong tất cả object tạo từ lớp chứa khối
C. Trong toàn bộ method kể cả trước lệnh khai báo
D. Trong phạm vi khối từ điểm khai báo trở đi
Đáp án đúng: D

Câu 10. Trong method có biến local `count` trùng field `count`, `this.count` chỉ gì?
A. Biến local `count` gần vị trí đang chạy nhất
B. Tham số method `count` được khai báo sau cùng
C. Field `count` thuộc đối tượng hiện tại
D. Field `count` thuộc superclass bất kể override
Đáp án đúng: C

Câu 11. Với `if (condition) ... else ...` và điều kiện boolean, nhánh nào chạy?
A. Nhánh else chạy trước rồi mới tới nhánh if
B. Nhánh if luôn chạy trước khi kiểm tra điều kiện
C. Chỉ nhánh tương ứng giá trị điều kiện
D. Cả hai nhánh chạy rồi chọn kết quả hợp lệ
Đáp án đúng: C

Câu 12. Trong chuỗi `if / else if / else`, nếu hai điều kiện đầu đều đúng thì sao?
A. Thân nhánh `else` chạy sau cả hai điều kiện
B. Cả hai thân nhánh điều kiện đúng đều chạy
C. Chỉ thân nhánh `else if` thứ hai được chạy
D. Chỉ thân nhánh `if` đầu tiên được thực thi
Đáp án đúng: D

Câu 13. Trong Java, `false && expensive()` có gọi `expensive()` không?
A. Có, vì method boolean bắt buộc được thực thi
B. Không, vì Java bỏ qua mọi method sau toán tử
C. Có, vì Java luôn đánh giá hai toán hạng trước
D. Không, vì `&&` dừng khi vế trái là false
Đáp án đúng: D

Câu 14. Trong Java, `true || expensive()` có gọi `expensive()` không?
A. Không, vì compiler xóa method khỏi mã nguồn
B. Có, vì `||` luôn tính cả hai toán hạng
C. Không, vì `||` dừng khi vế trái là true
D. Có, vì method gọi trong điều kiện phải chạy
Đáp án đúng: C

Câu 15. Với `int x=2; int y=++x;`, sau hai lệnh giá trị nào đúng?
A. `x` bằng `2` còn `y` bằng `3`
B. Cả `x` và `y` đều mang giá trị `3`
C. `x` bằng `3` còn `y` bằng `2`
D. Cả `x` và `y` đều mang giá trị `2`
Đáp án đúng: B

Câu 16. Trong `switch` Java dùng cú pháp nhánh `case A ->`, điều gì đúng?
A. `switch` luôn thử lại nhánh đầu sau khi chạy xong
B. Mọi nhánh sau đó vẫn chạy nếu thiếu `break`
C. Cú pháp mũi tên bắt buộc dùng `continue`
D. Không tự fall-through sang nhánh phía sau
Đáp án đúng: D

Câu 17. Vòng `while (condition)` có thể chạy phần thân bao nhiêu lần ít nhất?
A. Một lần dù điều kiện sai ngay từ đầu vòng
B. Không lần nào nếu điều kiện sai ngay từ đầu
C. Hai lần trước khi điều kiện được kiểm tra
D. Một lần cho mỗi nhánh có trong thân vòng
Đáp án đúng: B

Câu 18. Vòng `do { work(); } while (condition);` có đặc điểm nào?
A. Điều kiện được kiểm tra trước lời gọi `work()`
B. Vòng luôn chạy đúng một lần bất kể điều kiện
C. Chạy thân trước rồi mới kiểm tra điều kiện
D. Thân có thể bị bỏ qua nếu điều kiện ban đầu sai
Đáp án đúng: C

Câu 19. Vòng `for (int i=0; i<5; i++)` thực thi phần thân bao nhiêu lần?
A. Bốn lần, với `i` nhận các giá trị từ `1` đến `4`
B. Sáu lần, với `i` nhận các giá trị từ `0` đến `5`
C. Năm lần, với `i` đi từ `0` đến `4`
D. Năm lần, với `i` nhận các giá trị từ `1` đến `5`
Đáp án đúng: C

Câu 20. Khi `n > 0`, vòng `for (int i=1; i<=n; i++)` chạy bao nhiêu lần?
A. Đúng `n` lần vì gồm hai biên `1` và `n`
B. Đúng `n+1` lần vì xét từ `0` đến `n`
C. Đúng `2*n` lần vì tăng cả `i` lẫn `n`
D. Đúng `n-1` lần vì bỏ qua phần tử cuối
Đáp án đúng: A

Câu 21. Gặp `continue` trong một vòng `for`, điều nào xảy ra?
A. Bỏ qua mọi điều kiện lặp ở các vòng tiếp theo
B. Thoát hẳn vòng và tiếp tục sau dấu ngoặc đóng
C. Khởi động lại toàn bộ method chứa vòng hiện tại
D. Bỏ phần còn lại, rồi chạy bước cập nhật
Đáp án đúng: D

Câu 22. Với hai vòng lặp lồng nhau, `break` không nhãn trong vòng trong làm gì?
A. Chỉ bỏ qua một lần lặp của vòng trong hiện tại
B. Chuyển điều khiển thẳng về đầu vòng lặp ngoài
C. Thoát cả hai vòng lặp và kết thúc luôn method
D. Thoát vòng trong, vẫn tiếp tục vòng ngoài
Đáp án đúng: D

Câu 23. Hai vòng lặp lồng nhau có lần lượt `n` và `m` lượt độc lập có độ phức tạp nào?
A. `O(n^2+m^2)` vì vòng lặp tự nhân đôi chi phí
B. `O(n*m)` khi thân trong có chi phí hằng số
C. `O(n+m)` vì chỉ cần cộng hai số lượt lặp
D. `O(log(n*m))` vì vòng trong được tối ưu hóa
Đáp án đúng: B

Câu 24. Loop invariant được sử dụng chủ yếu để chứng minh điều gì?
A. Mọi vòng đều kết thúc trong thời gian hằng số
B. Một tính chất giữ đúng trước và sau mỗi vòng lặp
C. Giá trị các biến phải luôn giữ nguyên mỗi lượt
D. Mọi lệnh trong thân vòng đều không có side effect
Đáp án đúng: B

Câu 25. Trong chứng minh vòng lặp, loop variant thường là đại lượng nào?
A. Biểu thức chỉ đúng tại thời điểm khởi tạo vòng
B. Biến đếm có thể tăng không giới hạn ở mọi lượt
C. Đại lượng có cận dưới và giảm sau mỗi lượt
D. Biến toàn cục đổi giá trị theo luồng thực thi
Đáp án đúng: C

Câu 26. Với `while (i<n)` nhưng thân không đổi `i` và `n`, rủi ro chính là gì?
A. Vòng có thể không dừng nếu điều kiện luôn đúng
B. Vòng luôn tự kết thúc sau một lượt nhờ compiler
C. Vòng luôn bị chuyển thành câu lệnh `if` duy nhất
D. Vòng tự tăng `i` dù không có câu lệnh cập nhật
Đáp án đúng: A

Câu 27. Khi đọc số cho tới giá trị canh gác `-1`, điều kiện dừng phù hợp là gì?
A. Dừng xử lý sau một số lần đọc được cố định
B. Dừng xử lý khi tổng các giá trị nhập bằng `-1`
C. Dừng xử lý ngay khi giá trị nhập bằng `0`
D. Dừng xử lý ngay khi giá trị nhập bằng `-1`
Đáp án đúng: D

Câu 28. Để đếm số phần tử thỏa điều kiện trong vòng lặp, accumulator nên cập nhật ra sao?
A. Khởi tạo `count=0`, tăng khi phần tử được chấp nhận
B. Khởi tạo `count=1`, tăng sau mọi lần chạy vòng
C. Khởi tạo `count=0`, tăng cả khi điều kiện sai
D. Khởi tạo `count=n`, giảm khi phần tử được chấp nhận
Đáp án đúng: A

Câu 29. Xóa phần tử `ArrayList` ngay trong enhanced-for bằng `list.remove(x)` gây rủi ro nào?
A. Luôn ném `IndexOutOfBoundsException` đầu vòng
B. Tự khóa toàn bộ list nên không thể có lỗi duyệt
C. Có thể phát sinh `ConcurrentModificationException`
D. Luôn xóa an toàn vì for-each giữ bản sao list
Đáp án đúng: C

Câu 30. Khi làm việc với file trong Java, cơ chế nào giúp đóng tài nguyên khi gặp exception?
A. Dùng `try-with-resources` để tự đóng tài nguyên
B. Chỉ gọi `flush()` thay cho thao tác đóng file
C. Đóng file chỉ ở cuối nhánh thành công của method
D. Chờ GC chạy rồi tự động đồng bộ file xuống đĩa
Đáp án đúng: A

Câu 31. Việc tách một đoạn lặp lại thành method có tên rõ ràng giúp cải thiện gì?
A. Loại bỏ mọi side effect của đoạn chương trình gốc
B. Bảo đảm chi phí runtime luôn giảm theo cấp số nhân
C. Buộc JVM thực thi mọi method trong một thread riêng
D. Giảm trùng lặp và gom hành vi vào một điểm bảo trì
Đáp án đúng: D

Câu 32. Một method thay đổi field của object nhận vào có hệ quả nào?
A. Mọi sửa đổi chỉ tồn tại trong stack frame của method
B. Caller luôn nhận bản sao object mới sau khi method chạy
C. Method không thể sửa trạng thái vì tham số truyền giá trị
D. Caller có thể quan sát trạng thái object đã thay đổi
Đáp án đúng: D

Câu 33. Trong hàm đệ quy, base case có vai trò chủ yếu nào?
A. Buộc mọi lời gọi đệ quy phải chạy song song
B. Cung cấp điều kiện dừng không gọi tiếp đệ quy
C. Giữ nguyên mọi biến local qua các lần gọi đệ quy
D. Tự động cấp phát heap cho mọi tham số tham chiếu
Đáp án đúng: B

Câu 34. Với Java, đệ quy quá sâu có thể dẫn đến điều gì?
A. `ClassCastException` do thiếu base case ở cuối
B. `StackOverflowError` do dùng quá nhiều stack frame
C. `OutOfMemoryError` luôn xảy ra trước tràn stack
D. `IllegalStateException` vì JVM cấm đệ quy sâu
Đáp án đúng: B

Câu 35. Khi gặp `return` trong một method, luồng điều khiển bình thường chuyển đi đâu?
A. Tiếp tục thực thi những lệnh sau `return` trong method
B. Quay lại đầu method để kiểm tra điều kiện ban đầu
C. Dừng ngay toàn bộ JVM và hủy mọi thread đang chạy
D. Trở về điểm gọi method sau khi xử lý các khối `finally`
Đáp án đúng: D

Câu 36. Guard clause `if (!valid) return;` thường mang lại lợi ích gì?
A. Chuyển toàn bộ nhánh còn lại thành tác vụ bất đồng bộ
B. Buộc các điều kiện kiểm tra sau luôn được thực thi
C. Xử lý trường hợp không hợp lệ sớm, giảm mức lồng nhau
D. Bảo đảm method không bao giờ ném bất kỳ exception nào
Đáp án đúng: C

Câu 37. Trong thiết kế theo hợp đồng, precondition mô tả điều gì?
A. Điều phải đúng trước khi gọi một thủ tục hay method
B. Điều chỉ được kiểm tra sau khi method kết thúc
C. Trạng thái luôn đúng ở mọi vòng lặp trong method
D. Giá trị mặc định JVM tự gán cho mọi tham số
Đáp án đúng: A

Câu 38. Vì sao không nên dùng `assert` Java làm kiểm tra dữ liệu đầu vào bắt buộc?
A. Assertion được JVM tự chuyển thành khóa đồng bộ
B. Assertion chỉ hỗ trợ biến primitive không hỗ trợ object
C. Assertion có thể bị tắt nên kiểm tra không được chạy
D. Assertion luôn chuyển exception thành giá trị trả về
Đáp án đúng: C

Câu 39. Trong nhiều `catch` liên quan kế thừa Java, quy tắc sắp xếp đúng là gì?
A. Chỉ được dùng một `catch` khi các lỗi có kế thừa
B. Bắt supertype trước subtype để tránh bỏ lọt lỗi
C. Bắt subtype trước supertype để tránh nhánh không tới
D. Bất kỳ thứ tự nào cũng được vì JVM tự sắp xếp
Đáp án đúng: C

Câu 40. Với nhiều tài nguyên trong `try-with-resources`, thứ tự đóng thông thường là gì?
A. Đóng theo thứ tự ngược với thứ tự tạo tài nguyên
B. Đóng đồng thời mọi tài nguyên trong một lời gọi
C. Không tự đóng nếu khối `try` ném ngoại lệ
D. Đóng theo đúng thứ tự đã tạo các tài nguyên
Đáp án đúng: A

Câu 41. Với checked exception được gọi từ Java method, caller thường phải làm gì?
A. Luôn dùng `System.exit()` để bảo toàn trạng thái
B. Xử lý bằng `catch` hoặc khai báo `throws` phù hợp
C. Tự động bỏ qua lỗi vì compiler đã kiểm tra tên lớp
D. Chỉ cần đặt `final` lên biến nhận kết quả lời gọi
Đáp án đúng: B

Câu 42. Từ khóa `throw` khác `throws` trong Java ở điểm nào?
A. `throw` ném đối tượng lỗi; `throws` khai báo lỗi có thể ném
B. `throw` khai báo loại lỗi; `throws` tạo đối tượng lỗi
C. Cả hai đều chỉ dùng trong phần khai báo của method
D. Cả hai đều ném cùng một exception ngay khi gọi method
Đáp án đúng: A

Câu 43. Khi bọc ngoại lệ trong lỗi nghiệp vụ mới, hành động nào giữ được nguyên nhân ban đầu?
A. Gọi `fillInStackTrace()` rồi xóa thông tin lỗi gốc
B. Chỉ ghi tên lớp exception gốc vào log rồi bỏ đối tượng
C. Thay `cause` bằng `null` để tránh phụ thuộc tầng dưới
D. Truyền exception gốc làm `cause` của exception mới
Đáp án đúng: D

Câu 44. Một thủ tục đã sửa hai field rồi thất bại trước bước thứ ba có rủi ro gì?
A. Để lại trạng thái thay đổi một phần nếu không rollback
B. Luôn tự hoàn tác tất cả phép gán khi ném exception
C. Luôn đưa object về trạng thái ban đầu khi gặp `catch`
D. Không thể quan sát trạng thái phần vì method chưa return
Đáp án đúng: A

Câu 45. Hai thread cùng làm `counter++` trên biến chung không đồng bộ gặp nguy cơ gì?
A. Luôn xảy ra deadlock trước khi cập nhật được biến
B. Mất lần cập nhật vì thao tác đọc-sửa-ghi không nguyên tử
C. Mỗi thread luôn có bản sao độc lập của biến chung
D. Luôn cho kết quả đúng vì toán tử `++` là nguyên tử
Đáp án đúng: B

Câu 46. Khai báo `volatile int count` có đủ làm `count++` nguyên tử giữa thread không?
A. Có; `volatile` tự khóa mọi câu lệnh chứa biến chung
B. Có; `volatile` luôn dùng CAS khi thực hiện toán tử tăng
C. Không; `volatile` làm giá trị biến không thể bị thay đổi
D. Không; `volatile` không biến phép tăng thành thao tác nguyên tử
Đáp án đúng: D

Câu 47. Để kiểm thử method dùng một counter mutable nội bộ giữa nhiều ca, nên làm gì?
A. Cho các ca chạy song song mà không reset trạng thái chung
B. Đưa counter về trạng thái biết trước ở đầu mỗi ca kiểm thử
C. Chỉ so số lần gọi method thay vì kiểm tra kết quả nhận
D. Dùng kết quả counter từ ca trước để dự đoán ca sau
Đáp án đúng: B

Câu 48. Khi refactor một vòng lặp mệnh lệnh, phép kiểm chứng nào đáng tin cậy nhất?
A. Giả định mọi refactor giữ nguyên kết quả mà không test
B. Giữ bất biến hành vi qua test với biên và dữ liệu lỗi
C. Chỉ kiểm tra số dòng sau refactor giảm so với trước
D. Chỉ kiểm tra mã mới có ít biến local hơn trước
Đáp án đúng: B
