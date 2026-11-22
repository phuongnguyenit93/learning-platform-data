# Software Design Design Problem Technical Debt

Nợ kỹ thuật (technical debt) là cách diễn đạt những chi phí phát sinh trong tương lai khi cấu trúc và chất lượng nội bộ của phần mềm khiến việc sửa đổi khó hơn cần thiết. Không phải mọi đoạn mã chưa đẹp đều cần được viết lại ngay; điều quan trọng là hiểu nợ xuất hiện từ đâu, phần chi phí phát sinh khi nào và nó ảnh hưởng như thế nào tới khả năng phát triển sản phẩm. Module này cung cấp góc nhìn thiết kế lẫn quản trị để phân biệt nợ kỹ thuật với lỗi chức năng hoặc mong muốn cải tiến thông thường.

Roadmap một cấp gồm tám mốc: nắm ẩn dụ nợ gốc và lãi, nhận diện nguồn gốc và phân loại, tìm các dấu hiệu trong codebase, rồi đánh giá chi phí và ưu tiên xử lý. Các mốc tiếp theo hướng dẫn cách trả nợ từng bước qua refactoring an toàn, giảm nợ mới bằng quy trình chất lượng và theo dõi những khoản nợ còn lại trong kế hoạch phát triển.

Module dành cho người đã có kinh nghiệm lập trình cơ bản, tham gia bảo trì phần mềm hoặc làm việc cùng nhóm phát triển. Sau khi học, bạn có thể nhận diện và mô tả một khoản nợ kỹ thuật có bằng chứng, giải thích đánh đổi với công việc tính năng, chọn hướng cải tiến hợp lý và kiểm chứng tác động theo thời gian.