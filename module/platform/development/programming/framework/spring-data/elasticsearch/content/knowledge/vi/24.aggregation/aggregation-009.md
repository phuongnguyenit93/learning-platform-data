# Pipeline aggregation và tính toán từ kết quả nhóm

Aggregation của Elasticsearch thường bắt đầu bằng việc gom document thành các nhóm hoặc tính metric trên một tập dữ liệu. Ví dụ, hệ thống bán hàng có thể nhóm đơn hàng theo tháng, tính tổng doanh thu từng tháng, đếm số đơn và tính giá trị đơn trung bình. Sau khi có các kết quả nhóm này, ứng dụng có thể cần tính thêm doanh thu trung bình giữa các tháng, tổng doanh thu lũy kế, mức tăng trưởng, độ lệch giữa hai kỳ hoặc chỉ giữ lại những nhóm đạt một ngưỡng.

Pipeline aggregation giải quyết lớp tính toán tiếp theo đó. Thay vì đọc trực tiếp từng document, pipeline aggregation đọc kết quả của những aggregation khác rồi tính toán trên các bucket hoặc metric đã được tạo. Vì vậy, có thể xem pipeline aggregation là bước xử lý sau trên kết quả nhóm.

Elasticsearch chia pipeline aggregation thành hai nhóm chính:

- **Parent pipeline aggregation:** chạy bên trong một multi-bucket aggregation và tạo giá trị hoặc quyết định cho từng bucket của aggregation cha.
- **Sibling pipeline aggregation:** đặt cùng cấp với một multi-bucket aggregation, đọc các bucket của aggregation đó và tạo ra một kết quả tổng hợp ở cấp sibling.

Những phép tính phổ biến gồm derivative, cumulative_sum, moving function, bucket script, bucket selector, bucket sort, sum_bucket, avg_bucket, stats_bucket và percentiles_bucket. Trong Spring Data Elasticsearch, có thể xây dựng chúng bằng NativeQuery cùng Elasticsearch Java API Client builder.

## 1. Vì sao cần pipeline aggregation?

Giả sử index orders lưu các đơn hàng với các field:

    {
      "orderId": "o-1001",
      "createdAt": "2026-01-15T10:00:00Z",
      "amount": 250.0,
      "status": "PAID",
      "category": "keyboard"
    }

Một báo cáo doanh thu theo tháng cần:

1. Nhóm đơn hàng theo tháng.
2. Tính tổng amount trong từng tháng.
3. Tính doanh thu lũy kế từ đầu năm.
4. Tính mức thay đổi doanh thu giữa tháng hiện tại và tháng trước.
5. Tính doanh thu trung bình của các tháng.

Bước 1 và 2 là các aggregation thông thường: date_histogram và sum. Các bước 3, 4 và 5 là phép tính trên kết quả đã nhóm, vì vậy pipeline aggregation phù hợp.

Nếu ứng dụng tải toàn bộ kết quả nhóm về Java rồi tự tính, code có thể phải xử lý nhiều bucket, truyền nhiều dữ liệu qua mạng và tự quản lý các trường hợp bucket trống. Pipeline aggregation cho phép Elasticsearch thực hiện các phép tính này ngay trên kết quả aggregation của request search.

Pipeline aggregation không thay đổi document gốc và không ghi kết quả tính toán trở lại index. Nó chỉ bổ sung dữ liệu vào response của request search.

## 2. Aggregation thông thường và pipeline aggregation

Aggregation thông thường làm việc trên document được query chọn. Ví dụ:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            }
          }
        }
      }
    }

Kết quả tạo các bucket theo tháng. Mỗi bucket có doc_count và metric revenue.

Pipeline aggregation có thể tham chiếu metric revenue trong các bucket đó:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "revenue_change": {
              "derivative": {
                "buckets_path": "revenue"
              }
            }
          }
        },
        "average_monthly_revenue": {
          "avg_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        }
      }
    }

Trong ví dụ:

- date_histogram tạo các bucket theo tháng.
- sum tính revenue trong từng bucket.
- derivative là parent pipeline aggregation nằm bên trong sales_by_month và tính mức thay đổi so với bucket trước.
- avg_bucket là sibling pipeline aggregation ở cùng cấp với sales_by_month và tính trung bình metric revenue trên các bucket tháng.

Aggregation thông thường tạo dữ liệu đầu vào. Pipeline aggregation đọc dữ liệu đó và thực hiện phép tính bổ sung.

## 3. Bucket path là gì?

Pipeline aggregation không nhận trực tiếp một field document như amount. Nó nhận một đường dẫn đến metric hoặc thuộc tính bucket do aggregation khác tạo ra. Đường dẫn này được gọi là buckets_path.

Một số dạng thường gặp:

| Dạng path | Ý nghĩa |
|---|---|
| revenue | Metric con có tên revenue trong bucket hiện tại |
| sales_by_month>revenue | Metric revenue nằm trong aggregation sales_by_month |
| by_category>by_month>revenue | Metric revenue trong aggregation lồng nhiều cấp |
| sales_by_month>_count | Số document trong mỗi bucket tháng |
| sales_by_month>_key | Khóa của bucket, khi loại pipeline hỗ trợ bucket key |
| stats.avg | Thuộc tính avg của một multi-value metric aggregation có tên stats |

Dấu > dùng để đi qua các aggregation/bucket lồng nhau. Với multi-value metric, dấu chấm dùng để chọn thuộc tính cụ thể như avg, min hoặc max.

Ví dụ:

    "buckets_path": "sales_by_month>revenue"

Path này yêu cầu pipeline đọc metric revenue từ từng bucket do sales_by_month tạo ra.

Với bucket_script có nhiều đầu vào, có thể đặt tên biến trong map:

    "buckets_path": {
      "revenue": "revenue_sum",
      "cost": "cost_sum"
    }

Script có thể sử dụng params.revenue và params.cost.

### Bucket path phải trỏ đến kết quả phù hợp

Pipeline aggregation cần một metric số hoặc một thuộc tính bucket mà loại pipeline đó hỗ trợ. Không thể dùng bucket path tùy ý để đọc một field document chưa được aggregation tính ra.

Nếu cần tính tổng amount, trước hết tạo sum aggregation trên amount. Sau đó pipeline mới tham chiếu đến tên aggregation sum.

## 4. Parent và sibling pipeline aggregation

Sự khác nhau giữa parent và sibling quyết định vị trí khai báo và dạng kết quả.

### Parent pipeline aggregation

Parent pipeline aggregation được khai báo bên trong một multi-bucket aggregation. Nó chạy trên từng bucket của aggregation cha.

Ví dụ:

    "sales_by_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        },
        "running_revenue": {
          "cumulative_sum": {
            "buckets_path": "revenue"
          }
        }
      }
    }

running_revenue tạo giá trị cho từng bucket tháng, dựa trên tổng doanh thu của tháng đó và các bucket trước.

Các parent pipeline aggregation thường gặp:

- derivative
- cumulative_sum
- moving_fn
- serial_diff
- bucket_script
- bucket_selector
- bucket_sort

Một parent pipeline aggregation cần được đặt dưới một multi-bucket aggregation phù hợp, ví dụ date_histogram, histogram, terms hoặc composite trong những trường hợp API hỗ trợ.

### Sibling pipeline aggregation

Sibling pipeline aggregation được đặt cùng cấp với multi-bucket aggregation mà nó đọc. Nó tổng hợp các bucket thành một kết quả metric ở cấp sibling.

Ví dụ:

    "sales_by_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        }
      }
    },
    "average_monthly_revenue": {
      "avg_bucket": {
        "buckets_path": "sales_by_month>revenue"
      }
    }

average_monthly_revenue là một metric kết quả ở cấp aggregation gốc. Nó không tạo thêm bucket tháng.

Các sibling pipeline aggregation thường gặp:

- min_bucket
- max_bucket
- sum_bucket
- avg_bucket
- stats_bucket
- extended_stats_bucket
- percentiles_bucket

Một cách nhớ:

- Parent: tính toán trên từng bucket của aggregation cha.
- Sibling: đọc một tập bucket và tạo kết quả tổng hợp ở cùng cấp.

## 5. sum_bucket, avg_bucket, min_bucket và max_bucket

Đây là các sibling pipeline aggregation cơ bản. Chúng tính một metric từ cùng một metric trong nhiều bucket.

Ví dụ tính doanh thu trung bình và tổng doanh thu của các tháng:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            }
          }
        },
        "total_revenue_across_months": {
          "sum_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        },
        "average_monthly_revenue": {
          "avg_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        },
        "lowest_monthly_revenue": {
          "min_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        },
        "highest_monthly_revenue": {
          "max_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        }
      }
    }

Các pipeline này trả về một giá trị metric. Chúng không tạo danh sách bucket mới.

### Khi nào dùng?

- sum_bucket: tổng doanh thu của các tháng hoặc tổng số lượng của các nhóm.
- avg_bucket: trung bình metric giữa các nhóm.
- min_bucket: tìm nhóm có metric thấp nhất.
- max_bucket: tìm nhóm có metric cao nhất.

Chú ý rằng avg_bucket tính trung bình trên các bucket, không mặc nhiên là trung bình trên từng document. Nếu các tháng có số đơn khác nhau, trung bình doanh thu tháng và trung bình amount của mỗi đơn là hai đại lượng khác nhau.

## 6. stats_bucket và extended_stats_bucket

stats_bucket tính các thống kê cơ bản trên metric của nhiều bucket:

- count
- min
- max
- avg
- sum

Ví dụ:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            }
          }
        },
        "monthly_revenue_stats": {
          "stats_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        }
      }
    }

extended_stats_bucket bổ sung các thống kê mở rộng như phương sai và độ lệch chuẩn:

    "monthly_revenue_extended_stats": {
      "extended_stats_bucket": {
        "buckets_path": "sales_by_month>revenue"
      }
    }

Những metric này hữu ích cho báo cáo tổng quan, ví dụ doanh thu tháng cao nhất, thấp nhất, trung bình và mức phân tán giữa các tháng.

Không nhầm stats_bucket với stats aggregation thông thường:

- stats tính thống kê trên giá trị field của document trong tập dữ liệu.
- stats_bucket tính thống kê trên kết quả metric đã được tính cho từng bucket.

## 7. percentiles_bucket

percentiles_bucket tính percentile trên các giá trị metric của các bucket. Ví dụ, muốn biết ngưỡng doanh thu tháng mà 90% các tháng không vượt quá:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            }
          }
        },
        "monthly_revenue_percentiles": {
          "percentiles_bucket": {
            "buckets_path": "sales_by_month>revenue",
            "percents": [
              50,
              90,
              99
            ]
          }
        }
      }
    }

Percentile 50 tương ứng median gần đúng của phân phối bucket metric; percentile 90 và 99 thể hiện các ngưỡng cao hơn.

Đây là percentile trên doanh thu từng tháng, không phải percentile trên amount của từng đơn hàng. Muốn percentile của giá trị đơn hàng, dùng percentiles aggregation thông thường trên field amount.

## 8. derivative: tính mức thay đổi giữa các bucket

derivative tính đạo hàm rời rạc của một metric theo thứ tự bucket. Trong báo cáo theo tháng, nó thường được dùng để xem doanh thu tăng hay giảm so với tháng trước.

Ví dụ:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "monthly_change": {
              "derivative": {
                "buckets_path": "revenue"
              }
            }
          }
        }
      }
    }

Nếu doanh thu các tháng là:

| Tháng | Revenue | Derivative |
|---|---:|---:|
| Tháng 1 | 100 | null |
| Tháng 2 | 130 | 30 |
| Tháng 3 | 120 | -10 |
| Tháng 4 | 160 | 40 |

Derivative của tháng đầu không có giá trị vì không có bucket trước để so sánh. Giá trị dương biểu thị metric tăng, giá trị âm biểu thị metric giảm.

### Derivative không phải phần trăm tăng trưởng

Derivative trong ví dụ là chênh lệch tuyệt đối giữa hai bucket:

    current - previous

Nếu cần phần trăm thay đổi:

    (current - previous) / previous * 100

có thể dùng bucket_script kết hợp metric hiện tại và derivative, hoặc dùng bucket_script tham chiếu metric phù hợp. Cần xử lý trường hợp previous bằng 0 để tránh chia cho 0.

## 9. cumulative_sum: tổng lũy kế

cumulative_sum tính tổng tích lũy của metric qua các bucket theo thứ tự:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month",
            "order": {
              "_key": "asc"
            }
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "running_revenue": {
              "cumulative_sum": {
                "buckets_path": "revenue"
              }
            }
          }
        }
      }
    }

Ví dụ:

| Tháng | Revenue | Running revenue |
|---|---:|---:|
| Tháng 1 | 100 | 100 |
| Tháng 2 | 130 | 230 |
| Tháng 3 | 120 | 350 |
| Tháng 4 | 160 | 510 |

Ứng dụng thường dùng cumulative_sum cho:

- Doanh thu lũy kế từ đầu năm.
- Số đơn lũy kế.
- Lượt truy cập tích lũy.
- Số sự kiện tích lũy theo thời gian.

Thứ tự bucket rất quan trọng. Với date_histogram, nên khai báo order theo _key tăng dần nếu cần tổng lũy kế theo thời gian từ cũ đến mới.

## 10. moving_fn: tính toán trên cửa sổ trượt

moving_fn tính một hàm trên một cửa sổ gồm một số bucket gần nhau. Ví dụ tính trung bình doanh thu ba tháng gần nhất để làm mượt biến động:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month",
            "min_doc_count": 0
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "moving_average_3_months": {
              "moving_fn": {
                "buckets_path": "revenue",
                "window": 3,
                "script": "MovingFunctions.unweightedAvg(values)"
              }
            }
          }
        }
      }
    }

window là số bucket trong cửa sổ, không phải số ngày. Với date_histogram theo tháng, window 3 thường tương ứng ba bucket tháng. Với histogram theo ngày, window 7 tương ứng bảy bucket ngày.

MovingFunctions cung cấp các hàm Painless được hỗ trợ như unweightedAvg, max, min, sum và một số phép tính khác. Có thể viết script tùy chỉnh khi cần công thức riêng, nhưng nên dùng hàm có sẵn nếu đã đáp ứng mục tiêu.

### moving_fn và moving_avg

Trong các phiên bản Elasticsearch cũ có moving_avg pipeline aggregation. API này đã được thay thế bằng moving_fn trong các phiên bản mới. Khi làm dự án hiện tại, hãy ưu tiên moving_fn và kiểm tra phiên bản cluster nếu đang duy trì hệ thống cũ.

### Window và bucket trống

moving_fn phụ thuộc vào số bucket và cách xử lý bucket thiếu dữ liệu. Nếu tháng không có đơn hàng, date_histogram mặc định có thể không tạo bucket cho tháng đó. Khi cần chuỗi thời gian liên tục, hãy xem xét min_doc_count: 0 và extended_bounds, rồi chọn gap_policy phù hợp.

## 11. serial_diff: chênh lệch với bucket trước đó

serial_diff tính chênh lệch giữa giá trị hiện tại và giá trị cách đó một số bucket xác định bằng lag.

Ví dụ so sánh doanh thu tháng này với cùng tháng cách đây 12 tháng:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month",
            "min_doc_count": 0
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "year_over_year_difference": {
              "serial_diff": {
                "buckets_path": "revenue",
                "lag": 12
              }
            }
          }
        }
      }
    }

lag bằng 12 nghĩa là so sánh với bucket cách 12 vị trí trong chuỗi bucket. Nếu mỗi bucket là một tháng, đây là chênh lệch so với 12 tháng trước.

serial_diff trả về chênh lệch tuyệt đối, không phải tỷ lệ phần trăm. Muốn tính phần trăm, có thể kết hợp với bucket_script và xử lý mẫu số bằng 0.

## 12. bucket_script: tính công thức cho từng bucket

bucket_script là parent pipeline aggregation cho phép tính một metric mới từ nhiều metric trong cùng bucket. Nó dùng script với các biến được khai báo trong buckets_path.

Ví dụ tính lợi nhuận theo tháng:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "shipping_cost": {
              "sum": {
                "field": "shippingCost"
              }
            },
            "profit_after_shipping": {
              "bucket_script": {
                "buckets_path": {
                  "revenue": "revenue",
                  "shipping": "shipping_cost"
                },
                "script": "params.revenue - params.shipping"
              }
            }
          }
        }
      }
    }

Trong mỗi bucket tháng:

- revenue tham chiếu metric tổng amount.
- shipping tham chiếu metric tổng shippingCost.
- Script tính revenue trừ shipping.
- Kết quả profit_after_shipping được trả về như một metric của bucket.

Có thể dùng bucket_script để tính:

- Tỷ lệ chuyển đổi từ số đơn và số lượt truy cập.
- Giá trị đơn trung bình từ tổng doanh thu và số đơn.
- Tỷ lệ lợi nhuận.
- Phần trăm thay đổi so với kỳ trước nếu có metric tương ứng.

### Chia và xử lý giá trị bằng 0

Ví dụ tính giá trị đơn trung bình:

    "average_order_value": {
      "bucket_script": {
        "buckets_path": {
          "revenue": "revenue",
          "orders": "_count"
        },
        "script": "params.orders == 0 ? 0 : params.revenue / params.orders"
      }
    }

Trong một số trường hợp, dùng metric value_count trên orderId sẽ rõ ràng hơn nếu một document không đại diện cho một đơn hàng. _count là số document trong bucket, không phải số đơn nghiệp vụ nếu mỗi đơn có nhiều document.

Script cần trả về một số hợp lệ. Hãy xác định hành vi khi mẫu số bằng 0, metric thiếu hoặc bucket không có dữ liệu.

## 13. bucket_selector: lọc bucket theo kết quả tính toán

bucket_selector là parent pipeline aggregation dùng script boolean để giữ hoặc loại từng bucket. Ví dụ chỉ giữ tháng có doanh thu ít nhất 100.000:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "qualified_months": {
              "bucket_selector": {
                "buckets_path": {
                  "monthlyRevenue": "revenue"
                },
                "script": "params.monthlyRevenue >= 100000"
              }
            }
          }
        }
      }
    }

Bucket selector không lọc document trước khi aggregation chạy. Nó được thực thi sau khi các bucket và metric đã được tính, rồi loại bucket không thỏa điều kiện khỏi response.

Điểm này có ý nghĩa về hiệu năng: bucket_selector giúp response chỉ còn các bucket cần thiết, nhưng không làm Elasticsearch bỏ qua việc tính aggregation cho những bucket bị loại. Nếu điều kiện có thể biểu diễn bằng query/filter trên document, dùng filter trước aggregation thường hiệu quả hơn.

### Phân biệt bucket_selector và query filter

- Query filter loại document trước khi aggregation tính toán.
- bucket_selector loại bucket sau khi metric trong bucket đã được tính.

Ví dụ chỉ lấy đơn hàng PAID là điều kiện document, nên đặt status trong bool filter. Ví dụ chỉ hiển thị tháng có doanh thu vượt 100.000 là điều kiện trên metric của bucket, nên dùng bucket_selector.

## 14. bucket_sort: sắp xếp và giới hạn bucket

bucket_sort là parent pipeline aggregation dùng để sắp xếp, bỏ qua hoặc giới hạn bucket đã được tạo bởi aggregation cha.

Ví dụ lấy 5 category có tổng doanh thu cao nhất:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_category": {
          "terms": {
            "field": "category",
            "size": 100
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "top_categories": {
              "bucket_sort": {
                "sort": [
                  {
                    "revenue": {
                      "order": "desc"
                    }
                  }
                ],
                "size": 5
              }
            }
          }
        }
      }
    }

bucket_sort sắp xếp các bucket theo metric revenue rồi giữ lại 5 bucket đầu.

### Giới hạn quan trọng của bucket_sort

bucket_sort chỉ làm việc trên các bucket mà aggregation cha đã tạo. Trong ví dụ, terms size là 100, vì vậy bucket_sort chỉ có thể sắp xếp tối đa 100 category được terms aggregation trả về.

Nếu terms chỉ tạo 10 bucket, bucket_sort size 50 không thể tự tìm thêm 40 category khác. Muốn top 5 chính xác trong toàn bộ tập category, cần bảo đảm aggregation cha đã thu thập đủ candidate theo semantics và giới hạn của terms. Với yêu cầu duyệt toàn bộ bucket theo trang, hãy cân nhắc composite aggregation thay vì dùng bucket_sort như một cơ chế phân trang không giới hạn.

bucket_sort có thể nhận from và size để cắt danh sách bucket sau khi sort. Đây là phân trang trên tập bucket đã tạo, không tương đương search_after trên document.

## 15. Gap policy và bucket không có dữ liệu

Pipeline aggregation theo chuỗi thời gian có thể gặp bucket thiếu metric. Ví dụ tháng 2 không có đơn hàng nên date_histogram mặc định có thể không tạo bucket cho tháng đó, hoặc bucket được tạo nhưng metric không có giá trị.

Các pipeline aggregation hỗ trợ gap_policy để quyết định cách xử lý khoảng trống. Hai lựa chọn thường gặp:

- skip: bỏ qua bucket thiếu giá trị trong phép tính.
- insert_zeros: xem giá trị thiếu như 0.

Ví dụ:

    "monthly_change": {
      "derivative": {
        "buckets_path": "revenue",
        "gap_policy": "insert_zeros"
      }
    }

Nếu doanh thu tháng 2 không có dữ liệu, insert_zeros xem metric của tháng đó là 0 khi tính derivative. Với skip, bucket thiếu metric được bỏ qua theo semantics của pipeline.

Không nên chọn insert_zeros chỉ để làm biểu đồ trông liền mạch. Cần xác định bucket trống có nghĩa là không phát sinh doanh thu hay dữ liệu chưa được thu thập. Hai trường hợp này khác nhau về nghiệp vụ.

## 16. Tạo bucket thời gian liên tục

date_histogram mặc định chỉ tạo bucket có document phù hợp. Nếu cần hiển thị cả tháng không có đơn hàng, có thể dùng min_doc_count: 0 và extended_bounds:

    GET orders/_search
    {
      "size": 0,
      "query": {
        "range": {
          "createdAt": {
            "gte": "2026-01-01T00:00:00Z",
            "lt": "2027-01-01T00:00:00Z"
          }
        }
      },
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month",
            "min_doc_count": 0,
            "extended_bounds": {
              "min": "2026-01-01T00:00:00Z",
              "max": "2026-12-01T00:00:00Z"
            }
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "running_revenue": {
              "cumulative_sum": {
                "buckets_path": "revenue",
                "gap_policy": "insert_zeros"
              }
            }
          }
        }
      }
    }

min_doc_count: 0 yêu cầu tạo bucket rỗng trong phạm vi phù hợp; extended_bounds xác định biên thời gian muốn hiển thị. Query range giới hạn dữ liệu đầu vào. Khi dùng timezone hoặc calendar interval, cần chọn mốc biên theo timezone nghiệp vụ.

Nếu không có bucket cho một khoảng thời gian, pipeline không thể tự tạo bucket đó. Cần cấu hình histogram để tạo chuỗi bucket mong muốn trước.

## 17. Pipeline aggregation trên bucket lồng nhau

Aggregation có thể lồng nhiều cấp, ví dụ nhóm theo category rồi nhóm theo tháng:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "by_category": {
          "terms": {
            "field": "category"
          },
          "aggs": {
            "sales_by_month": {
              "date_histogram": {
                "field": "createdAt",
                "calendar_interval": "month"
              },
              "aggs": {
                "revenue": {
                  "sum": {
                    "field": "amount"
                  }
                },
                "running_revenue": {
                  "cumulative_sum": {
                    "buckets_path": "revenue"
                  }
                }
              }
            },
            "average_monthly_revenue": {
              "avg_bucket": {
                "buckets_path": "sales_by_month>revenue"
              }
            }
          }
        }
      }
    }

Ở đây:

- by_category tạo bucket cho từng category.
- sales_by_month tạo bucket tháng bên trong từng category.
- running_revenue tính lũy kế riêng trong từng category.
- average_monthly_revenue tính trung bình doanh thu tháng trong phạm vi category hiện tại.

Khi viết bucket path, phải xác định pipeline đang ở cấp nào và metric nằm trong aggregation con nào. Path tương đối với vị trí pipeline được khai báo; ví dụ revenue trong sales_by_month được tham chiếu bằng sales_by_month>revenue khi pipeline nằm ở cấp cha của sales_by_month.

## 18. Tính tỷ lệ chuyển đổi từ các bucket metric

Một báo cáo marketing có thể nhóm theo campaign và tính số lượt truy cập cùng số đơn hàng. Sau đó bucket_script tính conversion rate:

    GET campaign_events/_search
    {
      "size": 0,
      "aggs": {
        "by_campaign": {
          "terms": {
            "field": "campaign"
          },
          "aggs": {
            "visits": {
              "filter": {
                "term": {
                  "eventType": "visit"
                }
              }
            },
            "orders": {
              "filter": {
                "term": {
                  "eventType": "order"
                }
              }
            },
            "conversion_rate": {
              "bucket_script": {
                "buckets_path": {
                  "visits": "visits>_count",
                  "orders": "orders>_count"
                },
                "script": "params.visits == 0 ? 0 : params.orders / params.visits * 100"
              }
            }
          }
        }
      }
    }

Ở đây, visits và orders là filter aggregation, mỗi aggregation tạo một bucket đơn có doc_count. Pipeline script đọc _count của hai bucket và tính phần trăm.

Cần bảo đảm dữ liệu sự kiện có semantics phù hợp. Nếu một người có thể tạo nhiều event visit hoặc order, conversion rate theo số event có thể khác conversion rate theo số người dùng duy nhất. Nếu cần unique users, phải thiết kế cardinality hoặc dữ liệu tổng hợp tương ứng.

## 19. Tính tăng trưởng phần trăm qua bucket_script

Để tính tăng trưởng doanh thu tháng so với tháng trước, có thể kết hợp derivative với bucket_script. Một cách tiếp cận là dùng derivative làm tử số và doanh thu hiện tại trừ derivative để suy ra giá trị bucket trước:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "revenue_change": {
              "derivative": {
                "buckets_path": "revenue"
              }
            },
            "growth_percent": {
              "bucket_script": {
                "buckets_path": {
                  "current": "revenue",
                  "change": "revenue_change"
                },
                "script": "params.current - params.change == 0 ? 0 : params.change / (params.current - params.change) * 100"
              }
            }
          }
        }
      }
    }

Vì derivative = current - previous, biểu thức current - change suy ra previous. Script xử lý mẫu số bằng 0 bằng cách trả 0 trong ví dụ. Tùy nghiệp vụ, có thể muốn trả null/không có giá trị hoặc đánh dấu riêng thay vì coi tăng trưởng bằng 0 khi tháng trước không có doanh thu.

Đối với báo cáo cần công thức dễ đọc hơn, có thể dùng pipeline phù hợp để lấy metric kỳ trước hoặc thiết kế phép tính trong ứng dụng sau khi lấy các bucket. Cần kiểm tra khả năng tham chiếu pipeline aggregation theo phiên bản và không tạo dependency vòng giữa các pipeline.

## 20. Thứ tự thực thi và phụ thuộc giữa các aggregation

Pipeline aggregation chạy sau aggregation thông thường mà nó phụ thuộc. Vì vậy:

- Metric đầu vào phải được khai báo ở đúng vị trí trong aggregation tree.
- Parent pipeline phải nằm bên trong multi-bucket aggregation phù hợp.
- Sibling pipeline phải tham chiếu một multi-bucket aggregation cùng cấp.
- Pipeline không thể tự đọc field document như một metric nếu chưa có aggregation tạo ra giá trị đó.
- Không tạo vòng phụ thuộc giữa các pipeline.

Ví dụ cấu trúc:

    sales_by_month
      revenue
      revenue_change
      running_revenue
      revenue_selector

    average_monthly_revenue

revenue_change và running_revenue là parent pipeline trong sales_by_month. average_monthly_revenue là sibling pipeline ở cấp ngoài.

Nếu một pipeline cần kết quả của pipeline khác, phải bảo đảm đường dẫn và thứ tự phụ thuộc được Elasticsearch hỗ trợ. Với logic phức tạp, nên tách phép tính thành các tầng aggregation rõ ràng hoặc xử lý phần cuối ở ứng dụng để tránh query khó bảo trì.

## 21. Pipeline aggregation và hiệu năng

Pipeline aggregation không đọc lại toàn bộ document theo cách một query mới. Nó làm việc trên các kết quả aggregation đã được tạo. Tuy nhiên, điều đó không có nghĩa pipeline luôn miễn phí.

Chi phí tổng thể còn phụ thuộc:

- Số lượng document được query chọn.
- Số lượng bucket mà aggregation cha tạo.
- Độ sâu và số lượng aggregation lồng nhau.
- Số lượng pipeline function.
- Độ phức tạp của script.
- Kích thước response.

Một số nguyên tắc:

- Thu hẹp document bằng query/filter trước khi aggregate.
- Giới hạn số bucket nếu báo cáo không cần toàn bộ nhóm.
- Dùng date_histogram interval phù hợp với độ phân giải cần thiết.
- Tránh tạo hàng trăm nghìn bucket nếu chỉ cần top N.
- Dùng bucket_selector để lọc response khi điều kiện phụ thuộc metric; hiểu rằng nó chạy sau khi bucket đã được tính.
- Giữ script ngắn và dùng pipeline dựng sẵn khi có thể.
- Không dùng bucket_sort thay thế composite aggregation cho việc duyệt toàn bộ bucket theo cursor.
- Đo thời gian truy vấn và kích thước response trên dữ liệu gần production.

### Terms và top bucket

terms aggregation thường trả một số bucket giới hạn. Nếu pipeline tính toán trên kết quả terms, nó chỉ nhìn thấy các bucket được aggregation cha trả về theo semantics và giới hạn của terms. Hãy cấu hình size và shard_size phù hợp nếu cần top bucket chính xác hơn, hoặc cân nhắc composite để duyệt tất cả nhóm.

## 22. Pipeline aggregation trong Spring Data Elasticsearch

Trong Spring Data Elasticsearch hiện đại, có thể xây dựng aggregation bằng Elasticsearch Java API Client và gắn vào NativeQuery. Ví dụ nhóm doanh thu theo tháng, tính derivative và average bucket:

    Aggregation revenueByMonth = Aggregation.of(a -> a
        .dateHistogram(h -> h
            .field("createdAt")
            .calendarInterval(CalendarInterval.Month)
        )
        .aggregations("revenue", Aggregation.of(metric -> metric
            .sum(sum -> sum.field("amount"))
        ))
        .aggregations("revenue_change", Aggregation.of(pipeline -> pipeline
            .derivative(derivative -> derivative
                .bucketsPath("revenue")
            )
        ))
    );

    Aggregation averageMonthlyRevenue = Aggregation.of(a -> a
        .avgBucket(avg -> avg
            .bucketsPath("sales_by_month>revenue")
        )
    );

    NativeQuery query = NativeQuery.builder()
        .withAggregation("sales_by_month", revenueByMonth)
        .withAggregation("average_monthly_revenue", averageMonthlyRevenue)
        .build();

    SearchHits<Order> hits =
        operations.search(query, Order.class);

Ở ví dụ này:

- Aggregation revenueByMonth chứa date histogram và metric sum.
- revenue_change là parent pipeline aggregation nằm trong date histogram.
- averageMonthlyRevenue là sibling pipeline aggregation ở cấp query.
- NativeQuery gắn hai aggregation bằng tên để bucket path tham chiếu được.
- ElasticsearchOperations thực thi request.

Các import cơ bản:

    import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
    import co.elastic.clients.elasticsearch._types.CalendarInterval;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;
    import org.springframework.data.elasticsearch.core.SearchHits;
    import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

Tên enum, builder method và overload add aggregation phụ thuộc phiên bản Elasticsearch Java API Client. Hãy dùng dependency được Spring Boot/Spring Data quản lý và kiểm tra API thực tế của dự án.

### Dùng query chỉ lấy aggregation

Nếu request chỉ cần báo cáo aggregation, không cần trả danh sách document:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .range(r -> r
                .date(d -> d
                    .field("createdAt")
                    .gte("2026-01-01T00:00:00Z")
                    .lt("2027-01-01T00:00:00Z")
                )
            )
        )
        .withMaxResults(0)
        .withAggregation("sales_by_month", revenueByMonth)
        .withAggregation("average_monthly_revenue", averageMonthlyRevenue)
        .build();

    SearchHits<Order> hits =
        operations.search(query, Order.class);

Việc đặt max results bằng 0 giúp chỉ lấy aggregation response, không tải hit document không cần thiết. Tên API cấu hình size có thể khác theo phiên bản; nếu NativeQueryBuilder không có withMaxResults trong dependency hiện tại, dùng tùy chọn tương ứng của Query hoặc client.

## 23. Đọc aggregation response trong Spring Data

Khi gọi operations.search, kết quả trả về SearchHits. Aggregation response nằm trong phần aggregations của kết quả tìm kiếm; nó không nằm trong content của entity.

Ví dụ khái quát:

    SearchHits<Order> searchHits =
        operations.search(query, Order.class);

    AggregationsContainer<?> aggregations =
        searchHits.getAggregations();

Kiểu container và cách lấy aggregation cụ thể phụ thuộc phiên bản Spring Data Elasticsearch và client integration. Một số phiên bản cung cấp wrapper cho Elasticsearch Java API Client response; các phiên bản cũ có thể dùng abstraction khác.

Khi đọc response, cần:

1. Lấy aggregation container từ SearchHits.
2. Lấy aggregation theo tên đã khai báo, ví dụ sales_by_month hoặc average_monthly_revenue.
3. Kiểm tra đúng kiểu aggregation trả về: date histogram buckets, single-value metric hoặc pipeline result.
4. Duyệt buckets nếu cần hiển thị từng kỳ.
5. Đọc metric value của pipeline theo cấu trúc response tương ứng.

Không nên ép mọi aggregation thành một kiểu cụ thể mà không kiểm tra variant. Elasticsearch Java API Client dùng tagged union cho các loại aggregation/result; cần truy cập đúng variant và kiểm tra trường hợp response thiếu hoặc không đúng kiểu.

### Tách aggregation khỏi entity mapping

Entity Order mô tả document lưu trong index. Aggregation response là dữ liệu báo cáo được tính từ nhiều document. Không nên kỳ vọng Spring Data tự ánh xạ bucket thành một Order hoặc tự gán pipeline metric vào field entity.

Với dashboard, có thể chuyển aggregation response thành DTO riêng:

    public record MonthlyRevenue(
        String month,
        double revenue,
        Double revenueChange,
        Double runningRevenue
    ) {}

DTO này biểu diễn dữ liệu báo cáo, không phải document gốc.

## 24. Pipeline aggregation với bucket_script trong Java Client

Ví dụ tạo bucket_script tính lợi nhuận:

    Aggregation profit = Aggregation.of(a -> a
        .bucketScript(script -> script
            .bucketsPath(Map.of(
                "revenue", "revenue",
                "cost", "cost"
            ))
            .script(Script.of(s -> s
                .inline(inline -> inline
                    .source("params.revenue - params.cost")
                )
            ))
        )
    );

Aggregation cha:

    Aggregation salesByMonth = Aggregation.of(a -> a
        .dateHistogram(h -> h
            .field("createdAt")
            .calendarInterval(CalendarInterval.Month)
        )
        .aggregations("revenue", Aggregation.of(metric -> metric
            .sum(sum -> sum.field("amount"))
        ))
        .aggregations("cost", Aggregation.of(metric -> metric
            .sum(sum -> sum.field("cost"))
        ))
        .aggregations("profit", profit)
    );

    NativeQuery query = NativeQuery.builder()
        .withAggregation("sales_by_month", salesByMonth)
        .build();

Script là kiểu script của Elasticsearch Java API Client. Builder cụ thể có thể khác giữa phiên bản. Khi script nhận tham số động, nên truyền qua params thay vì nối chuỗi đầu vào vào source.

## 25. Pipeline aggregation với bucket_selector và bucket_sort

Có thể xây dựng bucket_selector để giữ lại bucket có doanh thu lớn hơn ngưỡng:

    Aggregation highRevenueOnly = Aggregation.of(a -> a
        .bucketSelector(selector -> selector
            .bucketsPath(Map.of(
                "revenue", "revenue"
            ))
            .script(Script.of(s -> s
                .inline(inline -> inline
                    .source("params.revenue >= params.minimum")
                )
            ))
        )
    );

Ví dụ bucket_sort:

    Aggregation topRevenueBuckets = Aggregation.of(a -> a
        .bucketSort(sort -> sort
            .sort(s -> s
                .field(f -> f
                    .field("revenue")
                    .order(SortOrder.Desc)
                )
            )
            .size(5)
        )
    );

Hai ví dụ minh họa cấu trúc Java Client. Tên overload cho script params, sort list và JsonData phụ thuộc phiên bản client; kiểm tra generated builder của dependency hiện tại trước khi dùng nguyên văn.

bucket_selector và bucket_sort phải được đặt dưới multi-bucket aggregation cha. Chúng thao tác trên bucket của aggregation cha chứ không lọc document đầu vào.

## 26. Khi nào nên tính trong Elasticsearch, khi nào tính trong Java?

Pipeline aggregation hữu ích khi phép tính:

- Dựa trên metric đã aggregate.
- Có thể biểu diễn bằng các pipeline function.
- Cần trả về cùng response với aggregation.
- Không cần logic nghiệp vụ phức tạp hoặc trạng thái ngoài Elasticsearch.

Tính trong Java có thể phù hợp hơn khi:

- Công thức cần dữ liệu từ nhiều nguồn.
- Cần xử lý business calendar hoặc quy tắc đặc thù.
- Cần nhiều bước xử lý khó diễn đạt bằng bucket path.
- Kết quả aggregation nhỏ và ứng dụng đã lấy dữ liệu cần thiết.
- Cần áp dụng logic có thể kiểm thử độc lập với Elasticsearch.

Không nên tải hàng triệu document về Java chỉ để tính tổng hoặc derivative mà Elasticsearch có thể làm trực tiếp. Ngược lại, không nên nhồi một quy trình nghiệp vụ lớn vào Painless script chỉ để giảm vài dòng Java.

Một ranh giới thực tế:

- Elasticsearch thực hiện filter, grouping, metric và phép tính trực tiếp trên bucket.
- Ứng dụng nhận kết quả tổng hợp, chuyển thành DTO và áp dụng logic trình bày hoặc phối hợp dữ liệu ngoài.

## 27. Các lỗi thường gặp

### Dùng field document trực tiếp trong buckets_path

Pipeline aggregation cần metric hoặc bucket property được aggregation tạo ra. Hãy tạo sum, avg, value_count hoặc metric phù hợp trước.

### Đặt parent pipeline sai cấp

Parent pipeline phải nằm bên trong multi-bucket aggregation mà nó xử lý. Nếu đặt ở cấp gốc như sibling pipeline, cấu trúc query sẽ không đúng.

### Nhầm parent và sibling

Derivative hoặc cumulative_sum thường tạo giá trị cho từng bucket nên đặt trong aggregation cha. avg_bucket hoặc sum_bucket tổng hợp nhiều bucket nên đặt cùng cấp với multi-bucket aggregation mà chúng đọc.

### Viết sai bucket path

Kiểm tra tên aggregation và cấp lồng nhau. Dùng dấu > để đi qua aggregation/bucket, và dấu chấm để truy cập thuộc tính của multi-value metric khi cần.

### Nghĩ avg_bucket là trung bình trên document

avg_bucket lấy trung bình các giá trị metric theo bucket. Nếu muốn trung bình amount trên từng document, dùng avg aggregation trực tiếp trên field amount.

### Nghĩ derivative là phần trăm tăng trưởng

Derivative thường là chênh lệch giữa các bucket. Muốn phần trăm, cần chia cho giá trị kỳ trước và xử lý trường hợp bằng 0.

### Bỏ qua bucket trống

Chuỗi thời gian có thể thiếu bucket. Quyết định dùng skip hay insert_zeros dựa trên ý nghĩa dữ liệu, và tạo bucket rỗng bằng min_doc_count/extended_bounds nếu cần.

### Dùng bucket_selector để giảm chi phí aggregation

bucket_selector chạy sau khi bucket và metric đã được tính. Nếu có thể lọc document trước bằng query/filter, hãy làm ở bước đó.

### Dùng bucket_sort để phân trang toàn bộ terms

bucket_sort chỉ sắp xếp các bucket đã được aggregation cha tạo. Với toàn bộ nhóm lớn và cần cursor pagination, cân nhắc composite aggregation.

### Script chia cho 0 hoặc đọc field thiếu

bucket_script cần xử lý metric thiếu và mẫu số bằng 0. Script score/metric phải trả về giá trị phù hợp với kiểu pipeline.

### Dùng pipeline aggregation để cập nhật dữ liệu

Pipeline aggregation chỉ tạo kết quả trong response. Nó không cập nhật document hoặc ghi metric vào index.

### Đọc aggregation như entity

Aggregation response không phải danh sách entity. Hãy đọc từ SearchHits aggregation container và ánh xạ sang DTO báo cáo.

## 28. Quy trình thiết kế pipeline aggregation

Khi xây dựng báo cáo, có thể thực hiện theo thứ tự:

1. Xác định document đầu vào bằng query và filter.
2. Chọn bucket aggregation phù hợp: date_histogram, histogram, terms hoặc composite.
3. Tạo metric cần thiết trong mỗi bucket: sum, avg, min, max, value_count hoặc metric khác.
4. Xác định phép tính cần chạy trên từng bucket hay trên toàn bộ bucket.
5. Dùng parent pipeline cho phép tính theo từng bucket như derivative, cumulative_sum, moving_fn, bucket_script hoặc bucket_selector.
6. Dùng sibling pipeline cho thống kê trên tập bucket như avg_bucket, sum_bucket, stats_bucket hoặc percentiles_bucket.
7. Viết buckets_path chính xác theo cây aggregation.
8. Quyết định gap_policy và cách tạo bucket rỗng.
9. Kiểm tra thứ tự bucket, đặc biệt với cumulative_sum, derivative và moving_fn.
10. Giới hạn số bucket và đánh giá chi phí script.
11. Gắn aggregation vào NativeQuery nếu dùng Spring Data Elasticsearch.
12. Đọc aggregation response theo đúng kiểu và chuyển thành DTO.
13. Kiểm thử với bucket trống, metric bằng 0, metric thiếu và dữ liệu biên.

## Kết luận

Pipeline aggregation thực hiện phép tính trên kết quả của các aggregation khác. Parent pipeline như derivative, cumulative_sum, moving_fn, serial_diff, bucket_script, bucket_selector và bucket_sort làm việc với từng bucket của multi-bucket aggregation cha. Sibling pipeline như sum_bucket, avg_bucket, min_bucket, max_bucket, stats_bucket và percentiles_bucket tổng hợp metric trên nhiều bucket thành kết quả ở cùng cấp.

Buckets_path là phần cốt lõi: nó chỉ đến metric hoặc bucket property mà pipeline cần đọc. Hãy tạo metric đầu vào trước, đặt pipeline đúng cấp, xử lý bucket trống bằng gap_policy và cấu hình histogram phù hợp. Trong Spring Data Elasticsearch, có thể dùng NativeQuery cùng Elasticsearch Java API Client Aggregation builder để gửi pipeline aggregation; kết quả cần được đọc từ aggregation container của SearchHits và chuyển sang DTO báo cáo. Dùng pipeline aggregation cho phép tính trên bucket, còn filter document, logic nghiệp vụ ngoài Elasticsearch và việc ghi dữ liệu vẫn thuộc các tầng tương ứng của ứng dụng.
